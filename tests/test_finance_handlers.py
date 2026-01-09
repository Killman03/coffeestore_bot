import pytest
from decimal import Decimal

from services.financial_service import FinancialService
from bot.handlers.finance import update_delivery_cost, process_delivery_cost
from bot.states import FinanceSettingsStates


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


class FakeCallbackMessage:
    def __init__(self):
        self.edits = []

    async def edit_text(self, text, **kwargs):
        self.edits.append(text)


class FakeCallback:
    def __init__(self):
        self.message = FakeCallbackMessage()

    async def answer(self, *args, **kwargs):
        return None


class FakeMessage:
    def __init__(self, text: str):
        self.text = text
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


@pytest.mark.asyncio
async def test_update_delivery_cost_starts_flow(transactional_session):
    session = transactional_session
    # Ensure there is a current settings record
    await FinancialService.get_or_create_default_settings(session)

    state = FakeState()
    callback = FakeCallback()

    await update_delivery_cost(callback, state, session)

    # State should be set to waiting for delivery cost input
    assert state.last_state == FinanceSettingsStates.waiting_for_delivery_cost
    # A message edit should be performed to prompt the user
    assert len(callback.message.edits) == 1
    assert "Изменение стоимости доставки" in callback.message.edits[0]


@pytest.mark.asyncio
async def test_process_delivery_cost_updates_settings_and_replies(transactional_session):
    session = transactional_session
    # Seed an initial settings value
    initial = await FinancialService.create_financial_settings(
        session,
        cny_to_som_rate=Decimal("12.34"),
        delivery_cost_per_kg=Decimal("300.00"),
        notes="seed",
    )

    state = FakeState()
    # You can change the input value here; assertion adapts to this value
    message = FakeMessage(text="222")

    await process_delivery_cost(message, state, session)

    # State should be cleared
    assert state.cleared is True

    # A confirmation message should be sent
    assert any("Стоимость доставки обновлена" in m for m in message.answers)

    # Current settings should reflect the new delivery cost
    current = await FinancialService.get_current_settings(session)
    assert current is not None
    expected_cost = Decimal(message.text.replace(",", "."))
    assert current.delivery_cost_per_kg == expected_cost

