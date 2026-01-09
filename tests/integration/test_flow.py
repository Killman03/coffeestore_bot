import pytest
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select

from database.models import Product, User, Sale
from services.product_service import ProductService
from services.user_service import UserService
from services.financial_service import FinancialService
from services.sale_service import SaleService


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_end_to_end_product_sale_flow(pg_session):
    session = pg_session

    # Ensure financial settings
    await FinancialService.get_or_create_default_settings(session)

    # Create product
    product = await ProductService.create_product(
        session,
        name="Integration Blend",
        base_price_cny=Decimal("18.00"),
        weight_kg=Decimal("0.400"),
    )

    # Create user
    user = await UserService.get_or_create_user(session, telegram_id=777777, username="int_seller")

    # Create sale
    sales = await SaleService.create_sale(
        session,
        product_id=product.id,
        seller_id=user.id,
        quantity=1,
        sale_price=Decimal("450.00"),
        sale_date=datetime.now(),
    )

    assert len(sales) == 1
    sale = sales[0]

    # Verify persisted via direct select
    result = await session.execute(select(Sale).where(Sale.id == sale.id))
    persisted = result.scalar_one_or_none()
    assert persisted is not None
    assert persisted.product_id == product.id
    assert persisted.seller_id == user.id


