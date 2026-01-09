from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, Iterable, List

from database.models import SupplyOrder, SupplyOrderItem, SupplyStatus, Product


_NOT_PROVIDED = object()


class SupplyService:
    """Service for supply order management."""
    
    @staticmethod
    async def create_supply_order(
        session: AsyncSession,
        tracking_number: str,
        order_date: datetime,
        items: list[tuple[int, int]],  # List of (product_id, quantity)
        notes: Optional[str] = None,
    ) -> SupplyOrder:
        """Create new supply order with items."""
        supply_order = SupplyOrder(
            tracking_number=tracking_number,
            order_date=order_date,
            status=SupplyStatus.IN_TRANSIT,
            notes=notes,
        )
        session.add(supply_order)
        await session.flush()  # Get ID before adding items
        
        # Add items
        for product_id, quantity in items:
            item = SupplyOrderItem(
                supply_order_id=supply_order.id,
                product_id=product_id,
                quantity=quantity,
            )
            session.add(item)
        
        await session.commit()
        await session.refresh(supply_order)
        # Re-fetch with related items and their products eagerly loaded
        result = await session.execute(
            select(SupplyOrder)
            .options(selectinload(SupplyOrder.items).selectinload(SupplyOrderItem.product))
            .where(SupplyOrder.id == supply_order.id)
        )
        return result.scalar_one()
    
    @staticmethod
    async def get_supply_order_by_id(session: AsyncSession, order_id: int) -> Optional[SupplyOrder]:
        """Get supply order by ID with items loaded."""
        result = await session.execute(
            select(SupplyOrder)
            .options(
                selectinload(SupplyOrder.items).selectinload(SupplyOrderItem.product)
            )
            .where(SupplyOrder.id == order_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_supply_order_by_tracking(session: AsyncSession, tracking_number: str) -> Optional[SupplyOrder]:
        """Get supply order by tracking number."""
        result = await session.execute(
            select(SupplyOrder)
            .options(
                selectinload(SupplyOrder.items).selectinload(SupplyOrderItem.product)
            )
            .where(SupplyOrder.tracking_number == tracking_number)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_all_supply_orders(session: AsyncSession, status: Optional[SupplyStatus] = None) -> list[SupplyOrder]:
        """Get all supply orders, optionally filtered by status."""
        query = select(SupplyOrder).options(
            selectinload(SupplyOrder.items).selectinload(SupplyOrderItem.product)
        )
        
        if status:
            query = query.where(SupplyOrder.status == status)
        
        query = query.order_by(SupplyOrder.order_date.desc())
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def update_supply_status(
        session: AsyncSession,
        order_id: int,
        status: SupplyStatus,
        delivery_date: Optional[datetime] = None,
    ) -> Optional[SupplyOrder]:
        """Update supply order status."""
        order = await SupplyService.get_supply_order_by_id(session, order_id)
        if not order:
            return None
        
        order.status = status
        if delivery_date:
            order.delivery_date = delivery_date
        elif status == SupplyStatus.DELIVERED and not order.delivery_date:
            order.delivery_date = datetime.now()
        
        await session.commit()
        await session.refresh(order)
        return order
    
    @staticmethod
    async def add_items_to_order(
        session: AsyncSession,
        order_id: int,
        items: list[tuple[int, int]],  # List of (product_id, quantity)
    ) -> bool:
        """Add items to existing supply order."""
        order = await SupplyService.get_supply_order_by_id(session, order_id)
        if not order:
            return False
        
        for product_id, quantity in items:
            item = SupplyOrderItem(
                supply_order_id=order_id,
                product_id=product_id,
                quantity=quantity,
            )
            session.add(item)
        
        await session.commit()
        return True

    @staticmethod
    async def mark_delivered_by_tracking(
        session: AsyncSession,
        tracking_numbers: Iterable[str],
        delivery_date: Optional[datetime] = None,
    ) -> list[SupplyOrder]:
        """Mark all orders with given tracking numbers as delivered.

        Returns list of updated orders (with items and products loaded).
        """
        updated: list[SupplyOrder] = []
        date_to_set = delivery_date or datetime.now()
        for tracking in tracking_numbers:
            order = await SupplyService.get_supply_order_by_tracking(session, tracking)
            if not order:
                continue
            order.status = SupplyStatus.DELIVERED
            order.delivery_date = order.delivery_date or date_to_set
            # ensure persistence
            session.add(order)
        await session.commit()

        # Re-query all updated for return with relationships
        for tracking in tracking_numbers:
            order = await SupplyService.get_supply_order_by_tracking(session, tracking)
            if order and order.status == SupplyStatus.DELIVERED:
                updated.append(order)
        return updated
    
    @staticmethod
    async def update_supply_item(
        session: AsyncSession,
        item_id: int,
        unit_price_cny: Decimal | None = _NOT_PROVIDED,
        unit_weight_kg: Decimal | None = _NOT_PROVIDED,
    ) -> Optional[SupplyOrderItem]:
        """Update cost parameters for a supply order item."""
        result = await session.execute(
            select(SupplyOrderItem)
            .options(
                selectinload(SupplyOrderItem.product),
                selectinload(SupplyOrderItem.supply_order),
            )
            .where(SupplyOrderItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return None
        
        if unit_price_cny is not _NOT_PROVIDED:
            item.unit_price_cny = unit_price_cny
        if unit_weight_kg is not _NOT_PROVIDED:
            item.unit_weight_kg = unit_weight_kg
        
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item
    
    @staticmethod
    async def get_arrival_dates(session: AsyncSession) -> List[date]:
        """Get all unique arrival dates (delivery_date) from delivered orders."""
        result = await session.execute(
            select(func.date(SupplyOrder.delivery_date).label('arrival_date'))
            .where(
                SupplyOrder.status == SupplyStatus.DELIVERED,
                SupplyOrder.delivery_date.isnot(None)
            )
            .distinct()
            .order_by(func.date(SupplyOrder.delivery_date).desc())
        )
        dates = result.scalars().all()
        return [d for d in dates if d is not None]
    
    @staticmethod
    async def get_items_by_arrival_date(
        session: AsyncSession,
        arrival_date: date
    ) -> List[SupplyOrderItem]:
        """Get all supply order items that arrived on the specified date."""
        arrival_start = datetime.combine(arrival_date, datetime.min.time())
        arrival_end = datetime.combine(arrival_date, datetime.max.time())
        
        result = await session.execute(
            select(SupplyOrderItem)
            .options(
                selectinload(SupplyOrderItem.supply_order),
                selectinload(SupplyOrderItem.product)
            )
            .join(SupplyOrderItem.supply_order)
            .where(
                SupplyOrder.status == SupplyStatus.DELIVERED,
                SupplyOrder.delivery_date >= arrival_start,
                SupplyOrder.delivery_date <= arrival_end
            )
            .order_by(SupplyOrderItem.id.desc())
        )
        return list(result.scalars().all())
    
    @staticmethod
    async def delete_supply_order(session: AsyncSession, order_id: int) -> bool:
        """Delete a supply order and purge all related warehouse data."""
        result = await session.execute(
            select(SupplyOrder)
            .options(selectinload(SupplyOrder.items))
            .where(SupplyOrder.id == order_id)
        )
        order = result.scalar_one_or_none()
        if not order:
            return False
        
        # Explicitly delete related supply items to ensure stock data is removed.
        await session.execute(
            delete(SupplyOrderItem).where(SupplyOrderItem.supply_order_id == order_id)
        )
        await session.delete(order)
        await session.commit()
        return True
    
    @staticmethod
    async def delete_supply_item(session: AsyncSession, item_id: int) -> bool:
        """Delete a supply order item by ID. Does not cascade delete sales."""
        result = await session.execute(
            select(SupplyOrderItem).where(SupplyOrderItem.id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return False
        
        await session.delete(item)
        await session.commit()
        return True

