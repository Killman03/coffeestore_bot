from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Category, Product, User, SupplyOrder, SupplyOrderItem, SupplyStatus, FinancialSettings


async def create_category(session: AsyncSession, name: str = "Test Category", description: Optional[str] = None) -> Category:
    category = Category(name=name, description=description)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def create_product(
    session: AsyncSession,
    *,
    name: str = "Test Product",
    category: Optional[Category] = None,
    base_price_cny: Decimal = Decimal("10.00"),
    weight_kg: Decimal = Decimal("0.250"),
    description: Optional[str] = None,
) -> Product:
    if category is None:
        category = await create_category(session)
    product = Product(
        name=name,
        category_id=category.id,
        base_price_cny=base_price_cny,
        weight_kg=weight_kg,
        description=description,
    )
    session.add(product)
    await session.commit()
    await session.refresh(product)
    return product


async def create_user(
    session: AsyncSession,
    *,
    telegram_id: int = 123456789,
    username: Optional[str] = "testuser",
    first_name: Optional[str] = "Test",
    last_name: Optional[str] = "User",
    is_admin: bool = False,
) -> User:
    full_name = f"{first_name} {last_name}" if first_name and last_name else (first_name or username or f"User {telegram_id}")
    user = User(
        telegram_id=telegram_id,
        username=username,
        first_name=first_name,
        last_name=last_name,
        full_name=full_name,
        is_admin=is_admin,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_financial_settings(
    session: AsyncSession,
    *,
    cny_to_som_rate: Decimal = Decimal("12.50"),
    delivery_cost_per_kg: Decimal = Decimal("350.00"),
    notes: Optional[str] = None,
) -> FinancialSettings:
    settings = FinancialSettings(
        cny_to_som_rate=cny_to_som_rate,
        delivery_cost_per_kg=delivery_cost_per_kg,
        is_active=True,
        notes=notes,
    )
    session.add(settings)
    await session.commit()
    await session.refresh(settings)
    return settings


async def create_supply_order(
    session: AsyncSession,
    *,
    tracking_number: str = "TRK-123",
    order_date: datetime | None = None,
    items: list[tuple[Product, int]] | None = None,
) -> SupplyOrder:
    if order_date is None:
        order_date = datetime.now()
    order = SupplyOrder(
        tracking_number=tracking_number,
        order_date=order_date,
        status=SupplyStatus.ORDERED,
    )
    session.add(order)
    await session.flush()

    if items:
        for product, quantity in items:
            session.add(
                SupplyOrderItem(
                    supply_order_id=order.id,
                    product_id=product.id,
                    quantity=quantity,
                )
            )

    await session.commit()
    await session.refresh(order)
    return order


