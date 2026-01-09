import pytest
from decimal import Decimal

from services.financial_service import FinancialService


@pytest.mark.asyncio
async def test_create_and_get_current_settings(transactional_session):
    session = transactional_session

    created = await FinancialService.create_financial_settings(
        session,
        cny_to_som_rate=Decimal("13.00"),
        delivery_cost_per_kg=Decimal("300.00"),
        notes="Initial",
    )
    assert created.is_active is True

    current = await FinancialService.get_current_settings(session)
    assert current is not None
    assert current.cny_to_som_rate == Decimal("13.00")


@pytest.mark.asyncio
async def test_update_settings_creates_new_active(transactional_session):
    session = transactional_session

    first = await FinancialService.create_financial_settings(
        session,
        cny_to_som_rate=Decimal("12.50"),
        delivery_cost_per_kg=Decimal("350.00"),
    )
    assert first.is_active is True

    updated = await FinancialService.update_settings(session, cny_to_som_rate=Decimal("12.75"))
    assert updated.is_active is True
    assert updated.cny_to_som_rate == Decimal("12.75")

    # Old becomes inactive
    all_settings = await FinancialService.get_all_settings(session)
    assert any(s.id == first.id and s.is_active is False for s in all_settings)


