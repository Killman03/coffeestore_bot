import asyncio
import os
import sys
from typing import AsyncGenerator, Callable

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

# Provide minimal environment so `config.Settings` can instantiate during imports
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DB_NAME", "test-db")
os.environ.setdefault("DB_USER", "test-user")
os.environ.setdefault("DB_PASSWORD", "test-pass")

# Ensure project root is on sys.path for imports like `database.models`
PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from database.models import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def async_engine():
    # Use in-memory SQLite for fast, isolated tests
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # Create tables once per test session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest.fixture()
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    SessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session


@pytest.fixture()
async def transactional_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Provides a session wrapped in a SAVEPOINT for test isolation.
    Rolls back after each test, keeping the metadata/tables intact.
    """
    SessionLocal = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_engine.connect() as connection:
        trans = await connection.begin()
        session = SessionLocal(bind=connection)
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


