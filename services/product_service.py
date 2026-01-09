from datetime import datetime, date
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional

from database.models import Product, SupplyOrderItem, Sale, SupplyStatus
from services.financial_service import FinancialService

# Sentinel value to distinguish between "not provided" and "explicitly set to None"
_NOT_PROVIDED = object()

ZERO = Decimal("0")
TWO_PLACES = Decimal("0.01")


class ProductService:
    """Service for product management."""
    
    @staticmethod
    async def create_product(
        session: AsyncSession,
        name: str,
        base_price_cny: Decimal,
        weight_kg: Decimal,
        description: Optional[str] = None,
        default_sale_price: Optional[Decimal] = None,
    ) -> Product:
        """Create new product."""
        product = Product(
            name=name,
            base_price_cny=base_price_cny,
            weight_kg=weight_kg,
            description=description,
            default_sale_price=default_sale_price,
        )
        session.add(product)
        await session.commit()
        await session.refresh(product)
        # Re-fetch (no relationships to load now)
        result = await session.execute(
            select(Product)
            .where(Product.id == product.id)
        )
        return result.scalar_one()
    
    @staticmethod
    async def get_product_by_id(session: AsyncSession, product_id: int) -> Optional[Product]:
        """Get product by ID."""
        result = await session.execute(
            select(Product)
            .where(Product.id == product_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_all_products(session: AsyncSession, active_only: bool = True) -> list[Product]:
        """Get all products."""
        query = select(Product)
        if active_only:
            query = query.where(Product.is_active == True)
        query = query.order_by(Product.name)
        
        result = await session.execute(query)
        return list(result.scalars().all())
    
    @staticmethod
    async def search_products(session: AsyncSession, search_term: str) -> list[Product]:
        """Search products by name."""
        term = (search_term or "").strip()
        query = select(Product).where(Product.is_active == True)
        if term:
            # Token-based contains search to be more forgiving
            for token in term.split():
                query = query.where(Product.name.ilike(f"%{token}%"))
        result = await session.execute(query.order_by(Product.name))
        return list(result.scalars().all())
    
    @staticmethod
    async def get_product_stock(session: AsyncSession, product_id: int) -> int:
        """Get current stock for product."""
        # Calculate total received from delivered orders
        received_result = await session.execute(
            select(func.coalesce(func.sum(SupplyOrderItem.quantity), 0))
            .join(SupplyOrderItem.supply_order)
            .where(SupplyOrderItem.product_id == product_id)
            .where(SupplyOrderItem.supply_order.has(status=SupplyStatus.DELIVERED))
        )
        total_received = received_result.scalar() or 0
        
        # Calculate total sold
        sold_result = await session.execute(
            select(func.coalesce(func.sum(Sale.quantity), 0))
            .where(Sale.product_id == product_id)
        )
        total_sold = sold_result.scalar() or 0
        
        return int(total_received - total_sold)
    
    @staticmethod
    async def get_products_with_stock(session: AsyncSession) -> list[tuple[Product, int]]:
        """Get all products with their current stock."""
        summaries = await ProductService.get_products_with_stock_summary(session)
        return [(product, stock) for product, stock, _ in summaries]

    @staticmethod
    async def get_products_with_stock_summary(
        session: AsyncSession,
    ) -> list[tuple[Product, int, Decimal]]:
        """Get active products with their stock quantity and total stock value."""
        products = await ProductService.get_all_products(session)
        if not products:
            return []

        default_settings = await FinancialService.get_or_create_default_settings(session)
        settings_cache: dict[date, object] = {}
        summaries: list[tuple[Product, int, Decimal]] = []

        for product in products:
            stock_qty, stock_value = await ProductService._calculate_stock_details_for_product(
                session,
                product,
                default_settings,
                settings_cache,
            )
            summaries.append((product, stock_qty, stock_value))

        return summaries
    
    @staticmethod
    async def update_product(
        session: AsyncSession,
        product_id: int,
        name: Optional[str] = _NOT_PROVIDED,
        base_price_cny: Optional[Decimal] = _NOT_PROVIDED,
        weight_kg: Optional[Decimal] = _NOT_PROVIDED,
        description: Optional[str] = _NOT_PROVIDED,
        default_sale_price: Optional[Decimal] = _NOT_PROVIDED,
    ) -> Optional[Product]:
        """Update product."""
        product = await ProductService.get_product_by_id(session, product_id)
        if not product:
            return None
        
        if name is not _NOT_PROVIDED:
            product.name = name
        if base_price_cny is not _NOT_PROVIDED:
            product.base_price_cny = base_price_cny
        if weight_kg is not _NOT_PROVIDED:
            product.weight_kg = weight_kg
        if description is not _NOT_PROVIDED:
            product.description = description
        if default_sale_price is not _NOT_PROVIDED:
            # Allow setting to None explicitly (when val == 0 in handler)
            product.default_sale_price = default_sale_price
        
        await session.commit()
        await session.refresh(product)
        return product
    
    @staticmethod
    async def deactivate_product(session: AsyncSession, product_id: int) -> bool:
        """Deactivate product (soft delete)."""
        product = await ProductService.get_product_by_id(session, product_id)
        if not product:
            return False
        
        product.is_active = False
        await session.commit()
        return True

    @staticmethod
    async def delete_product_and_supply_items(session: AsyncSession, product_id: int) -> bool:
        """Hard delete a product and purge all related supply items. 
        Cannot delete if product has sales records (use deactivate_product instead)."""
        product = await ProductService.get_product_by_id(session, product_id)
        if not product:
            return False
        
        # Check if product has any sales records
        sales_count_result = await session.execute(
            select(func.count(Sale.id)).where(Sale.product_id == product_id)
        )
        sales_count = sales_count_result.scalar() or 0
        
        if sales_count > 0:
            # Cannot delete product with sales records due to foreign key constraint
            # Return False to indicate deletion failed
            return False
        
        # Delete related supply items
        from sqlalchemy import delete
        await session.execute(delete(SupplyOrderItem).where(SupplyOrderItem.product_id == product_id))
        # Now delete product (safe since no sales exist)
        from sqlalchemy import delete as sqldelete
        await session.execute(sqldelete(Product).where(Product.id == product_id))
        await session.commit()
        return True

    @staticmethod
    async def _calculate_stock_details_for_product(
        session: AsyncSession,
        product: Product,
        default_settings,
        settings_cache: dict[date, object],
    ) -> tuple[int, Decimal]:
        """Calculate current stock quantity and total cost value for a product."""
        supply_items_result = await session.execute(
            select(SupplyOrderItem)
            .options(selectinload(SupplyOrderItem.supply_order))
            .where(SupplyOrderItem.product_id == product.id)
            .where(SupplyOrderItem.supply_order.has(status=SupplyStatus.DELIVERED))
        )
        supply_items = list(supply_items_result.scalars().all())
        supply_items.sort(
            key=lambda item: (
                item.supply_order.delivery_date
                or item.supply_order.order_date
                or datetime.min,
                item.id,
            )
        )

        total_delivered = sum(int(item.quantity or 0) for item in supply_items)

        sold_qty_result = await session.execute(
            select(func.coalesce(func.sum(Sale.quantity), 0)).where(Sale.product_id == product.id)
        )
        previously_sold_qty = int(sold_qty_result.scalar() or 0)

        current_stock = max(total_delivered - previously_sold_qty, 0)
        if current_stock <= 0:
            return current_stock, ZERO

        sold_to_deduct = max(previously_sold_qty, 0)
        remaining_stock_to_value = current_stock
        total_stock_value = ZERO

        async def get_settings_for_datetime(target_dt: datetime):
            cache_key = target_dt.date()
            if cache_key not in settings_cache:
                settings = await FinancialService.get_settings_for_date(session, target_dt)
                if not settings:
                    settings = default_settings
                settings_cache[cache_key] = settings
            return settings_cache[cache_key]

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

            take_qty = min(available_in_batch, remaining_stock_to_value)
            if take_qty <= 0:
                break

            arrival_dt = (
                item.supply_order.delivery_date
                or item.supply_order.order_date
                or datetime.now()
            )
            settings_for_batch = await get_settings_for_datetime(arrival_dt)

            unit_price_cny = item.unit_price_cny if item.unit_price_cny is not None else product.base_price_cny
            if unit_price_cny is None:
                unit_price_cny = ZERO

            unit_weight = item.unit_weight_kg if item.unit_weight_kg is not None else product.weight_kg
            if unit_weight is None:
                unit_weight = ZERO

            unit_cost = (
                (unit_price_cny * settings_for_batch.cny_to_som_rate)
                + (unit_weight * settings_for_batch.delivery_cost_per_kg)
            )

            total_stock_value += unit_cost * Decimal(take_qty)
            remaining_stock_to_value -= take_qty

            if remaining_stock_to_value <= 0:
                break

        if remaining_stock_to_value > 0:
            unit_price_cny = product.base_price_cny or ZERO
            unit_weight = product.weight_kg or ZERO
            fallback_unit_cost = (
                (unit_price_cny * default_settings.cny_to_som_rate)
                + (unit_weight * default_settings.delivery_cost_per_kg)
            )
            total_stock_value += fallback_unit_cost * Decimal(remaining_stock_to_value)

        total_stock_value = total_stock_value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        return current_stock, total_stock_value

