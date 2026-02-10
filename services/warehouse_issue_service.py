"""Service for warehouse issues (seller take from warehouse) and seller balances."""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional

from database.models import WarehouseIssue, Product, User, Sale, SupplyOrderItem, SupplyStatus


class WarehouseIssueService:
    """Service for recording and querying warehouse issues and seller stock."""

    @staticmethod
    async def get_warehouse_stock(session: AsyncSession, product_id: int) -> int:
        """Available quantity on warehouse for product (received - issued)."""
        received_result = await session.execute(
            select(func.coalesce(func.sum(SupplyOrderItem.quantity), 0))
            .join(SupplyOrderItem.supply_order)
            .where(SupplyOrderItem.product_id == product_id)
            .where(SupplyOrderItem.supply_order.has(status=SupplyStatus.DELIVERED))
        )
        total_received = received_result.scalar() or 0

        issued_result = await session.execute(
            select(func.coalesce(func.sum(WarehouseIssue.quantity), 0)).where(
                WarehouseIssue.product_id == product_id
            )
        )
        total_issued = issued_result.scalar() or 0
        return int(total_received - total_issued)

    @staticmethod
    async def create_issue(
        session: AsyncSession,
        seller_id: int,
        product_id: int,
        quantity: int,
    ) -> Optional[WarehouseIssue]:
        """Record seller taking quantity of product from warehouse. Returns None if not enough stock."""
        if quantity <= 0:
            return None
        available = await WarehouseIssueService.get_warehouse_stock(session, product_id)
        if quantity > available:
            return None
        issue = WarehouseIssue(
            seller_id=seller_id,
            product_id=product_id,
            quantity=quantity,
        )
        session.add(issue)
        await session.commit()
        await session.refresh(issue)
        result = await session.execute(
            select(WarehouseIssue)
            .options(
                selectinload(WarehouseIssue.seller),
                selectinload(WarehouseIssue.product),
            )
            .where(WarehouseIssue.id == issue.id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_seller_balance(
        session: AsyncSession,
        seller_id: int,
        product_id: int,
    ) -> int:
        """Current balance for seller and product: issued - sold."""
        issued_result = await session.execute(
            select(func.coalesce(func.sum(WarehouseIssue.quantity), 0)).where(
                WarehouseIssue.seller_id == seller_id,
                WarehouseIssue.product_id == product_id,
            )
        )
        issued = issued_result.scalar() or 0
        sold_result = await session.execute(
            select(func.coalesce(func.sum(Sale.quantity), 0)).where(
                Sale.seller_id == seller_id,
                Sale.product_id == product_id,
            )
        )
        sold = sold_result.scalar() or 0
        return int(issued - sold)

    @staticmethod
    async def get_all_seller_balances(
        session: AsyncSession,
    ) -> list[tuple[User, list[tuple[Product, int]]]]:
        """All sellers with list of (product, balance) where balance > 0."""
        sellers_result = await session.execute(
            select(User).where(User.is_active == True).order_by(User.full_name)
        )
        sellers = list(sellers_result.scalars().all())
        products_result = await session.execute(
            select(Product).where(Product.is_active == True).order_by(Product.name)
        )
        products = list(products_result.scalars().all())

        result: list[tuple[User, list[tuple[Product, int]]]] = []
        for seller in sellers:
            balances: list[tuple[Product, int]] = []
            for product in products:
                balance = await WarehouseIssueService.get_seller_balance(
                    session, seller.id, product.id
                )
                if balance > 0:
                    balances.append((product, balance))
            result.append((seller, balances))
        return result
