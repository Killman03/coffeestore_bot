import pytest
from datetime import datetime
from decimal import Decimal

from services.financial_service import FinancialService
from services.product_service import ProductService
from services.user_service import UserService
from services.sale_service import SaleService


@pytest.mark.asyncio
async def test_sale_cost_uses_updated_delivery_cost(transactional_session):
    session = transactional_session

    # Create product and user
    product = await ProductService.create_product(
        session,
        name="Pour Over",
        base_price_cny=Decimal("10.00"),
        weight_kg=Decimal("0.500"),
    )
    user = await UserService.get_or_create_user(session, telegram_id=999, username="tester")

    # Seed settings with delivery 300
    await FinancialService.create_financial_settings(
        session,
        cny_to_som_rate=Decimal("12.00"),
        delivery_cost_per_kg=Decimal("300.00"),
        notes="seed",
    )

    # Create a sale and capture cost via profit math
    sales1 = await SaleService.create_sale(
        session,
        product_id=product.id,
        seller_id=user.id,
        quantity=1,
        sale_price=Decimal("1000.00"),
        sale_date=datetime.now(),
    )
    assert len(sales1) == 1
    cost1 = sales1[0].cost_price

    # Update delivery cost to 350
    await FinancialService.update_settings(session, delivery_cost_per_kg=Decimal("350.00"))

    # Create another sale and ensure cost increased accordingly
    sales2 = await SaleService.create_sale(
        session,
        product_id=product.id,
        seller_id=user.id,
        quantity=1,
        sale_price=Decimal("1000.00"),
        sale_date=datetime.now(),
    )
    assert len(sales2) == 1
    cost2 = sales2[0].cost_price

    assert cost2 > cost1

