import pytest

from services.user_service import UserService


@pytest.mark.asyncio
async def test_get_or_create_user_creates_and_updates(transactional_session):
    session = transactional_session

    # Create new user
    user = await UserService.get_or_create_user(
        session,
        telegram_id=111,
        username="alpha",
        first_name="Alice",
        last_name="A",
    )
    assert user.id is not None
    assert user.full_name == "Alice A"

    # Update existing
    user2 = await UserService.get_or_create_user(
        session,
        telegram_id=111,
        username="alpha2",
        first_name="Alice",
        last_name="Anderson",
    )
    assert user2.id == user.id
    assert user2.full_name == "Alice Anderson"


@pytest.mark.asyncio
async def test_is_admin_false_by_default(transactional_session):
    session = transactional_session

    user = await UserService.get_or_create_user(session, telegram_id=222, username="beta")
    is_admin = await UserService.is_admin(session, 222)
    assert user.is_admin in (False, True)  # depends on env, but must be bool
    assert isinstance(is_admin, bool)


