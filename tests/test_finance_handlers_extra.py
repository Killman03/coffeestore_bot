import pytest
from decimal import Decimal

from bot.handlers.finance import menu_finance, update_delivery_cost, process_delivery_cost
from bot.states import FinanceSettingsStates
from services.financial_service import FinancialService


class FakeState:
    def __init__(self):
        self.last_state = None
        self.cleared = False

    async def set_state(self, state):
        self.last_state = state

    async def clear(self):
        self.cleared = True


class FakeMessage:
    def __init__(self, text: str = ""):
        self.text = text
        self.answers = []

    async def answer(self, text, **kwargs):
        self.answers.append(text)


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


@pytest.mark.asyncio
async def test_menu_finance_opens_settings(transactional_session):
    session = transactional_session
    state = FakeState()
    msg = FakeMessage()

    await menu_finance(msg, state, session)

    # State must switch to waiting_for_action
    assert state.last_state == FinanceSettingsStates.waiting_for_action
    # Should send a message with current params
    assert any("Финансовые настройки" in m for m in msg.answers)


@pytest.mark.asyncio
async def test_update_delivery_cost_without_existing_settings_creates_defaults(transactional_session):
    session = transactional_session
    # Ensure DB starts without settings; do not seed
    state = FakeState()
    cb = FakeCallback()

    await update_delivery_cost(cb, state, session)

    # Flow should prompt for new value
    assert state.last_state == FinanceSettingsStates.waiting_for_delivery_cost
    assert len(cb.message.edits) == 1
    assert "Изменение стоимости доставки" in cb.message.edits[0]


@pytest.mark.asyncio
async def test_process_delivery_cost_rejects_negative(transactional_session):
    session = transactional_session
    # Seed defaults to avoid None
    await FinancialService.get_or_create_default_settings(session)

    state = FakeState()
    msg = FakeMessage(text="-5")

    await process_delivery_cost(msg, state, session)

    # Should send validation error and not clear state
    assert any("Введите корректное неотрицательное число" in m for m in msg.answers)
    assert state.cleared is False


@pytest.mark.asyncio
async def test_process_delivery_cost_rejects_non_numeric(transactional_session):
    session = transactional_session
    await FinancialService.get_or_create_default_settings(session)

    state = FakeState()
    msg = FakeMessage(text="350 сом/кг")

    await process_delivery_cost(msg, state, session)

    # Should send validation error
    assert any("Введите корректное неотрицательное число" in m for m in msg.answers)
    assert state.cleared is False


