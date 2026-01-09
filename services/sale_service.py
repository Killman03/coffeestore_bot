from dataclasses import dataclass
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List

from database.models import Sale, Product, User, SupplyOrderItem, SupplyStatus
from services.financial_service import FinancialService

ZERO = Decimal("0")
TWO_PLACES = Decimal("0.01")


@dataclass
class SaleCostAllocation:
    quantity: int
    unit_cost: Decimal


class SaleService:
    """Service for sale management."""
    
    @staticmethod
    async def create_sale(
        session: AsyncSession,
        product_id: int,
        seller_id: int,
        quantity: int,
        sale_price: Decimal,
        sale_date: datetime,
        notes: Optional[str] = None,
    ) -> List[Sale]:
        """Create one or more sale records with automatic cost allocation.

        Returns list of created Sale objects (split by cost batches).
        """
        # Get product to calculate cost
        result = await session.execute(
            select(Product).where(Product.id == product_id)
        )
        product = result.scalar_one_or_none()
        if not product:
            return []
        
        allocations = await SaleService._allocate_costs(session, product, quantity, sale_date)
        if not allocations:
            return []

        created_ids: list[int] = []
        
        for allocation in allocations:
            unit_cost = allocation.unit_cost.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            profit_total = (sale_price - unit_cost) * allocation.quantity
            profit_total = profit_total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

            sale = Sale(
                product_id=product_id,
                seller_id=seller_id,
                quantity=allocation.quantity,
                sale_price=sale_price,
                cost_price=unit_cost,
                profit=profit_total,
                sale_date=sale_date,
                notes=notes,
            )
            session.add(sale)
            await session.flush()
            created_ids.append(sale.id)

        await session.commit()

        if not created_ids:
            return []

        # Re-fetch with related entities eagerly loaded to avoid async lazy loads in handlers
        result = await session.execute(
            select(Sale)
            .options(
                selectinload(Sale.product),
                selectinload(Sale.seller)
            )
            .where(Sale.id.in_(created_ids))
            .order_by(Sale.id.asc())
        )
        return list(result.scalars().all())
 
    @staticmethod
    async def _allocate_costs(
        session: AsyncSession,
        product: Product,
        sale_quantity: int,
        sale_date: datetime,
    ) -> List[SaleCostAllocation]:
        if sale_quantity <= 0:
            raise ValueError("Sale quantity must be positive")

        default_settings = await FinancialService.get_or_create_default_settings(session)

        base_price_cny = product.base_price_cny or ZERO
        product_weight = product.weight_kg or ZERO

        sale_date_settings = await FinancialService.get_settings_for_date(session, sale_date)
        if not sale_date_settings:
            sale_date_settings = default_settings

        fallback_unit_cost = (
            (base_price_cny * sale_date_settings.cny_to_som_rate)
            + (product_weight * sale_date_settings.delivery_cost_per_kg)
        )

        supply_items_result = await session.execute(
            select(SupplyOrderItem)
            .options(selectinload(SupplyOrderItem.supply_order))
            .where(SupplyOrderItem.product_id == product.id)
            .where(SupplyOrderItem.supply_order.has(status=SupplyStatus.DELIVERED))
        )
        supply_items = list(supply_items_result.scalars().all())

        if not supply_items:
            return [SaleCostAllocation(quantity=sale_quantity, unit_cost=fallback_unit_cost)]

        supply_items.sort(
            key=lambda item: (
                item.supply_order.delivery_date
                or item.supply_order.order_date
                or datetime.min,
                item.id,
            )
        )

        sold_qty_result = await session.execute(
            select(func.coalesce(func.sum(Sale.quantity), 0)).where(Sale.product_id == product.id)
        )
        previously_sold_qty = int(sold_qty_result.scalar() or 0)

        remaining_sale_qty = int(sale_quantity)
        if remaining_sale_qty <= 0:
            return [SaleCostAllocation(quantity=sale_quantity, unit_cost=fallback_unit_cost)]

        sold_to_deduct = previously_sold_qty
        settings_cache = {}
        allocations: List[SaleCostAllocation] = []

        async def get_settings_for_datetime(target_dt: datetime):
            cache_key = (target_dt.year, target_dt.month, target_dt.day)
            if cache_key in settings_cache:
                return settings_cache[cache_key]
            settings = await FinancialService.get_settings_for_date(session, target_dt)
            if not settings:
                settings = default_settings
            settings_cache[cache_key] = settings
            return settings

        for item in supply_items:
            batch_qty = int(item.quantity or 0)
            if batch_qty <= 0:
                continue

            if sold_to_deduct >= batch_qty:
                sold_to_deduct -= batch_qty
                continue

            available_in_batch = batch_qty - sold_to_deduct
            sold_to_deduct = 0
            if available_in_batch <= 0:
                continue

            arrival_dt = (
                item.supply_order.delivery_date
                or item.supply_order.order_date
                or sale_date
            )
            settings_for_batch = await get_settings_for_datetime(arrival_dt)

            unit_price_cny = (
                item.unit_price_cny if item.unit_price_cny is not None else base_price_cny
            )
            if unit_price_cny is None:
                unit_price_cny = ZERO

            unit_weight = (
                item.unit_weight_kg if item.unit_weight_kg is not None else product_weight
            )
            if unit_weight is None:
                unit_weight = ZERO

            batch_cost_per_unit = (
                (unit_price_cny * settings_for_batch.cny_to_som_rate)
                + (unit_weight * settings_for_batch.delivery_cost_per_kg)
            )

            take_qty = min(available_in_batch, remaining_sale_qty)
            if take_qty <= 0:
                continue

            allocations.append(SaleCostAllocation(quantity=take_qty, unit_cost=batch_cost_per_unit))
            remaining_sale_qty -= take_qty

            if remaining_sale_qty <= 0:
                break

        if remaining_sale_qty > 0:
            allocations.append(SaleCostAllocation(quantity=remaining_sale_qty, unit_cost=fallback_unit_cost))

        if not allocations:
            allocations.append(SaleCostAllocation(quantity=sale_quantity, unit_cost=fallback_unit_cost))

        return allocations

    @staticmethod
    async def get_sale_by_id(session: AsyncSession, sale_id: int) -> Optional[Sale]:
        """Get sale by ID with related data loaded."""
        result = await session.execute(
            select(Sale)
            .options(
                selectinload(Sale.product),
                selectinload(Sale.seller)
            )
            .where(Sale.id == sale_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_sales_by_date_range(
        session: AsyncSession,
        start_date: datetime,
        end_date: datetime,
        seller_id: Optional[int] = None,
        product_id: Optional[int] = None,
    ) -> list[Sale]:
        """Get sales within date range with optional filters."""
        query = select(Sale).options(
            selectinload(Sale.product),
            selectinload(Sale.seller)
        ).where(
            and_(
                Sale.sale_date >= start_date,
                Sale.sale_date <= end_date
            )
        )
        
        if seller_id:
            query = query.where(Sale.seller_id == seller_id)
        if product_id:
            query = query.where(Sale.product_id == product_id)
        
        query = query.order_by(Sale.sale_date.desc())
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def get_today_sales(session: AsyncSession, seller_id: Optional[int] = None) -> list[Sale]:
        """Get today's sales."""
        today_start = datetime.combine(date.today(), datetime.min.time())
        today_end = datetime.combine(date.today(), datetime.max.time())
        return await SaleService.get_sales_by_date_range(session, today_start, today_end, seller_id)
    
    @staticmethod
    async def get_month_sales(session: AsyncSession, year: int, month: int, seller_id: Optional[int] = None) -> list[Sale]:
        """Get sales for specific month."""
        start_date = datetime(year, month, 1)
        if month == 12:
            end_date = datetime(year + 1, 1, 1) - timedelta(seconds=1)
        else:
            end_date = datetime(year, month + 1, 1) - timedelta(seconds=1)
        
        return await SaleService.get_sales_by_date_range(session, start_date, end_date, seller_id)
    
    @staticmethod
    async def get_current_month_sales(session: AsyncSession, seller_id: Optional[int] = None) -> list[Sale]:
        """Get current month sales."""
        today = date.today()
        return await SaleService.get_month_sales(session, today.year, today.month, seller_id)
    
    @staticmethod
    async def calculate_total_profit(
        session: AsyncSession,
        start_date: datetime,
        end_date: datetime,
        seller_id: Optional[int] = None,
    ) -> Decimal:
        """Calculate total profit for date range."""
        query = select(func.coalesce(func.sum(Sale.profit), 0)).where(
            and_(
                Sale.sale_date >= start_date,
                Sale.sale_date <= end_date
            )
        )
        
        if seller_id:
            query = query.where(Sale.seller_id == seller_id)
        
        result = await session.execute(query)
        return Decimal(str(result.scalar() or 0))
    
    @staticmethod
    async def get_seller_statistics(
        session: AsyncSession,
        start_date: datetime,
        end_date: datetime,
    ) -> list[dict]:
        """Get sales statistics grouped by seller."""
        query = select(
            User.full_name,
            func.count(Sale.id).label('sales_count'),
            func.sum(Sale.quantity).label('total_quantity'),
            func.sum(Sale.sale_price * Sale.quantity).label('total_revenue'),
            func.sum(Sale.profit).label('total_profit'),
        ).join(
            Sale.seller
        ).where(
            and_(
                Sale.sale_date >= start_date,
                Sale.sale_date <= end_date
            )
        ).group_by(
            User.id, User.full_name
        ).order_by(
            func.sum(Sale.profit).desc()
        )
        
        result = await session.execute(query)
        rows = result.all()
        
        return [
            {
                'seller_name': row[0],
                'sales_count': row[1],
                'total_quantity': row[2],
                'total_revenue': Decimal(str(row[3] or 0)),
                'total_profit': Decimal(str(row[4] or 0)),
            }
            for row in rows
        ]
    
    @staticmethod
    async def get_sale_dates(session: AsyncSession) -> List[date]:
        """Get all unique sale dates."""
        result = await session.execute(
            select(func.date(Sale.sale_date).label('sale_date'))
            .distinct()
            .order_by(func.date(Sale.sale_date).desc())
        )
        dates = result.scalars().all()
        return [d for d in dates if d is not None]
    
    @staticmethod
    async def get_sales_by_date(session: AsyncSession, sale_date: date) -> List[Sale]:
        """Get all sales for a specific date."""
        date_start = datetime.combine(sale_date, datetime.min.time())
        date_end = datetime.combine(sale_date, datetime.max.time())
        return await SaleService.get_sales_by_date_range(session, date_start, date_end)
    
    @staticmethod
    async def delete_sale(session: AsyncSession, sale_id: int) -> bool:
        """Delete a sale by ID. Does not cascade delete."""
        result = await session.execute(
            select(Sale).where(Sale.id == sale_id)
        )
        sale = result.scalar_one_or_none()
        if not sale:
            return False
        
        await session.delete(sale)
        await session.commit()
        return True

