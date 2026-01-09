import pytest
from datetime import datetime
from decimal import Decimal
from sqlalchemy import select

from services.supply_service import SupplyService
from services.product_service import ProductService
from database.models import SupplyStatus, SupplyOrderItem


@pytest.mark.asyncio
async def test_create_and_get_supply_order(transactional_session):
    session = transactional_session

    p1 = await ProductService.create_product(session, name="Filter", base_price_cny=Decimal("3.00"), weight_kg=Decimal("0.100"))
    p2 = await ProductService.create_product(session, name="Gasket", base_price_cny=Decimal("2.00"), weight_kg=Decimal("0.050"))

    order = await SupplyService.create_supply_order(
        session,
        tracking_number="TRK-001",
        order_date=datetime.now(),
        items=[(p1.id, 10), (p2.id, 5)],
    )
    assert order.id is not None

    loaded = await SupplyService.get_supply_order_by_id(session, order.id)
    assert loaded is not None
    assert len(loaded.items) == 2


@pytest.mark.asyncio
async def test_update_supply_item_price(transactional_session):
    session = transactional_session

    product = await ProductService.create_product(
        session,
        name="Portafilter",
        base_price_cny=Decimal("10.00"),
        weight_kg=Decimal("0.400"),
    )

    order = await SupplyService.create_supply_order(
        session,
        tracking_number="TRK-EDIT-001",
        order_date=datetime.now(),
        items=[(product.id, 4)],
    )
    assert order.items
    item_id = order.items[0].id

    updated = await SupplyService.update_supply_item(
        session,
        item_id=item_id,
        unit_price_cny=Decimal("11.50"),
    )
    assert updated is not None
    assert updated.unit_price_cny == Decimal("11.50")


@pytest.mark.asyncio
async def test_update_supply_status_and_add_items(transactional_session):
    session = transactional_session

    p = await ProductService.create_product(session, name="Spoon", base_price_cny=Decimal("1.00"), weight_kg=Decimal("0.030"))

    order = await SupplyService.create_supply_order(session, tracking_number="TRK-002", order_date=datetime.now(), items=[(p.id, 2)])

    updated = await SupplyService.update_supply_status(session, order.id, SupplyStatus.DELIVERED)
    assert updated is not None
    assert updated.status == SupplyStatus.DELIVERED
    assert updated.delivery_date is not None

    ok = await SupplyService.add_items_to_order(session, order.id, [(p.id, 3)])
    assert ok is True


@pytest.mark.asyncio
async def test_delete_supply_order_removes_items_and_stock(transactional_session):
    session = transactional_session

    product = await ProductService.create_product(
        session,
        name="Tamper",
        base_price_cny=Decimal("5.00"),
        weight_kg=Decimal("0.150"),
    )
    order = await SupplyService.create_supply_order(
        session,
        tracking_number="TRK-DELETE-001",
        order_date=datetime.now(),
        items=[(product.id, 6)],
    )

    delivered = await SupplyService.update_supply_status(session, order.id, SupplyStatus.DELIVERED)
    assert delivered is not None

    stock_before = await ProductService.get_product_stock(session, product.id)
    assert stock_before == 6

    deleted = await SupplyService.delete_supply_order(session, order.id)
    assert deleted is True

    removed_order = await SupplyService.get_supply_order_by_id(session, order.id)
    assert removed_order is None

    remaining_items = await session.execute(
        select(SupplyOrderItem).where(SupplyOrderItem.supply_order_id == order.id)
    )
    assert list(remaining_items.scalars().all()) == []

    stock_after = await ProductService.get_product_stock(session, product.id)
    assert stock_after == 0
