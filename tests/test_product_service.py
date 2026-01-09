import pytest

from datetime import datetime, timezone
from decimal import Decimal

from database.models import SupplyOrder, SupplyOrderItem, SupplyStatus
from services.financial_service import FinancialService
from services.product_service import ProductService


@pytest.mark.asyncio
async def test_create_and_get_product(transactional_session):
    session = transactional_session

    product = await ProductService.create_product(
        session,
        name="Arabica",
        base_price_cny=Decimal("20.00"),
        weight_kg=Decimal("0.500"),
        description="Premium beans",
    )

    assert product.id is not None
    assert product.name == "Arabica"
    loaded = await ProductService.get_product_by_id(session, product.id)
    assert loaded is not None
    assert loaded.name == "Arabica"


@pytest.mark.asyncio
async def test_get_all_and_search_products(transactional_session):
    session = transactional_session
    await ProductService.create_product(session, name="Tamper", base_price_cny=Decimal("5.00"), weight_kg=Decimal("0.300"))
    await ProductService.create_product(session, name="Milk Pitcher", base_price_cny=Decimal("7.00"), weight_kg=Decimal("0.250"))

    all_products = await ProductService.get_all_products(session)
    assert len(all_products) >= 2

    matches = await ProductService.search_products(session, "Tamper")
    assert any(p.name == "Tamper" for p in matches)


@pytest.mark.asyncio
async def test_update_and_deactivate_product(transactional_session):
    session = transactional_session
    product = await ProductService.create_product(session, name="Cup", base_price_cny=Decimal("2.00"), weight_kg=Decimal("0.200"))

    updated = await ProductService.update_product(session, product.id, name="Mug")
    assert updated is not None
    assert updated.name == "Mug"

    ok = await ProductService.deactivate_product(session, product.id)
    assert ok is True


@pytest.mark.asyncio
async def test_stock_summary_includes_inventory_value(transactional_session):
    session = transactional_session
    product = await ProductService.create_product(
        session,
        name="Filter Coffee",
        base_price_cny=Decimal("6.00"),
        weight_kg=Decimal("0.500"),
    )

    default_settings = await FinancialService.get_or_create_default_settings(session)

    order = SupplyOrder(
        tracking_number="INV-001",
        order_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        delivery_date=datetime(2024, 1, 5, tzinfo=timezone.utc),
        status=SupplyStatus.DELIVERED,
    )
    session.add(order)
    await session.flush()

    item = SupplyOrderItem(
        supply_order_id=order.id,
        product_id=product.id,
        quantity=5,
        unit_price_cny=Decimal("6.00"),
    )
    session.add(item)
    await session.commit()

    summaries = await ProductService.get_products_with_stock_summary(session)
    assert len(summaries) == 1
    _, stock_qty, stock_value = summaries[0]

    assert stock_qty == 5
    unit_cost = (
        (Decimal("6.00") * default_settings.cny_to_som_rate)
        + (product.weight_kg * default_settings.delivery_cost_per_kg)
    )
    expected_value = (unit_cost * Decimal(5)).quantize(Decimal("0.01"))
    assert stock_value == expected_value
