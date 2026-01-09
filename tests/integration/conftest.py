import os
import ssl
import pytest

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.engine import make_url
from sqlalchemy import text


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


pytestmark = pytest.mark.integration


@pytest.fixture(scope="session")
def check_test_db_url():
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL is not set; skipping integration tests")
    return TEST_DATABASE_URL


@pytest.fixture(scope="session")
async def pg_engine(check_test_db_url):
    # Configure connect args; disable SSL for localhost to avoid Windows/asyncpg resets
    url = make_url(check_test_db_url)
    host = (url.host or "").lower()
    is_local = host in ("localhost", "127.0.0.1")
    connect_args = {"timeout": 30, "command_timeout": 30}

    # Respect sslmode from URL if provided; otherwise, default based on locality
    q = url.query or {}
    sslmode = q.get("sslmode") if isinstance(q, dict) else None
    if sslmode:
        sm = str(sslmode).lower()
        if sm in ("require", "verify-ca", "verify-full"):
            connect_args["ssl"] = ssl.create_default_context()
        elif sm in ("disable", "allow", "prefer"):
            connect_args["ssl"] = False
    else:
        connect_args["ssl"] = False if is_local else ssl.create_default_context()

    engine = create_async_engine(
        check_test_db_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        pool_recycle=1800,
        connect_args=connect_args,
    )
    try:
        # Warm-up connect
        async with engine.connect() as conn:
            await conn.scalar(text("SELECT 1"))
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture()
async def pg_session(pg_engine):
    SessionLocal = async_sessionmaker(pg_engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session


