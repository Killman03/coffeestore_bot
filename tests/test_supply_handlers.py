import pytest
from datetime import datetime

from aiogram import F

from bot.handlers.supply import auto_mark_delivered, arrival_confirm, arrival_manual, arrival_manual_input, menu_supply
from bot.states import ArrivalConfirmStates
from services.product_service import ProductService
from services.supply_service import SupplyService
from database.models import SupplyStatus


class FakeState:
    def __init__(self):
        self.last_state = None
        self.cleared = False
        self._data = {}

    async def set_state(self, state):
        self.last_state = state

    async def clear(self):
        self.cleared = True

    async def update_data(self, **kwargs):
        self._data.update(kwargs)

    async def get_data(self):
        return self._data


class FakeMessage:
    def __init__(self, text: str = ""):
        self.text = text
        self.answers = []
        self.edits = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)

    async def edit_text(self, text, **kwargs):
        self.edits.append(text)


class FakeCallback:
    def __init__(self):
        self.message = FakeMessage()
        self.data = ""

    async def answer(self, *args, **kwargs):
        return None


@pytest.mark.asyncio
async def test_auto_mark_delivered_confirmation_and_confirm(transactional_session):
    session = transactional_session

    # Create product and two supply orders (in transit)
    product = await ProductService.create_product(
        session,
        name="Test Dripper",
        base_price_cny=10,
        weight_kg=0.5,
    )
    order1 = await SupplyService.create_supply_order(session, tracking_number="TRK11111111", order_date=datetime.now(), items=[(product.id, 2)])
    order2 = await SupplyService.create_supply_order(session, tracking_number="TRK22222222", order_date=datetime.now(), items=[(product.id, 3)])
    assert order1.status == SupplyStatus.IN_TRANSIT

    state = FakeState()
    msg = FakeMessage(text="""
📦 Посылки прибыли в Бишкек - Тыныстанова 401:

📌 TRK11111111
📌 TRK22222222
⚖️ Вес посылок ИТОГО: 1.0 кг
💰 Стоимость ИТОГО: 100 с
    """.strip())

    await auto_mark_delivered(msg, session, state)

    # Should ask for confirmation
    assert state.last_state == ArrivalConfirmStates.waiting_for_confirmation
    assert any("Найдены следующие трек-номера" in a for a in msg.answers)

    # Confirm
    cb = FakeCallback()
    cb.data = "arrival_confirm"
    await arrival_confirm(cb, state, session)

    # Should edit with success and clear state
    assert any("Обновлены статусы" in e for e in cb.message.edits)
    assert state.cleared is True

    # Verify statuses changed
    updated1 = await SupplyService.get_supply_order_by_tracking(session, "TRK11111111")
    updated2 = await SupplyService.get_supply_order_by_tracking(session, "TRK22222222")
    assert updated1.status == SupplyStatus.DELIVERED
    assert updated2.status == SupplyStatus.DELIVERED


@pytest.mark.asyncio
async def test_auto_mark_delivered_manual_flow(transactional_session):
    session = transactional_session

    product = await ProductService.create_product(
        session,
        name="Scale",
        base_price_cny=8,
        weight_kg=0.3,
    )
    await SupplyService.create_supply_order(session, tracking_number="TRK33333333", order_date=datetime.now(), items=[(product.id, 1)])

    state = FakeState()
    msg = FakeMessage(text="📦 Посылки прибыли")
    # Start with a message that has no valid codes to exercise manual path
    await auto_mark_delivered(msg, session, state)
    # Since no codes found, bot advises about format
    assert any("Не удалось найти трек-номера" in a for a in msg.answers)

    # Now go via confirmation path with valid codes
    msg2 = FakeMessage(text="📌 TRK33333333")
    await auto_mark_delivered(msg2, session, state)
    cb = FakeCallback()
    cb.data = "arrival_manual"
    await arrival_manual(cb, state)

    # Provide manual input
    manual_msg = FakeMessage(text="""
📌 TRK33333333
⚖️ Вес посылок ИТОГО: 0.3 кг
    """.strip())
    await arrival_manual_input(manual_msg, state)
    # Should prompt again with confirmation
    assert any("Найдены следующие трек-номера" in a for a in manual_msg.answers)

    # Confirm
    cb2 = FakeCallback()
    cb2.data = "arrival_confirm"
    await arrival_confirm(cb2, state, session)

    updated = await SupplyService.get_supply_order_by_tracking(session, "TRK33333333")
    assert updated.status == SupplyStatus.DELIVERED


@pytest.mark.asyncio
async def test_menu_supply_shows_only_in_transit(transactional_session):
    session = transactional_session

    product = await ProductService.create_product(
        session,
        name="Kettle",
        base_price_cny=12,
        weight_kg=0.9,
    )
    # One in transit (by default), one delivered
    await SupplyService.create_supply_order(session, tracking_number="TRK_IN", order_date=datetime.now(), items=[(product.id, 1)])
    delivered = await SupplyService.create_supply_order(session, tracking_number="TRK_DEL", order_date=datetime.now(), items=[(product.id, 1)])
    await SupplyService.update_supply_status(session, delivered.id, SupplyStatus.DELIVERED)

    msg = FakeMessage()
    await menu_supply(msg, session)

    # Header should be 'В пути' and only TRK_IN present
    assert any("В пути:" in a for a in msg.answers)
    assert any("TRK_IN" in a for a in msg.answers)
    assert all("TRK_DEL" not in a for a in msg.answers)


