import os
import asyncio
import ssl
import pytest
import asyncpg
from sqlalchemy.engine import make_url


pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_engine_connects_and_has_tables(check_test_db_url):
    # Parse TEST_DATABASE_URL for asyncpg params
    url = make_url(check_test_db_url)
    host = url.host or "localhost"
    port = int(url.port or 5432)
    user = url.username or "postgres"
    password = url.password or ""
    database = url.database or "postgres"

    # SSL handling
    q = url.query or {}
    sslmode = q.get("sslmode") if isinstance(q, dict) else None
    if sslmode and str(sslmode).lower() in ("require", "verify-ca", "verify-full"):
        ssl_ctx = ssl.create_default_context()
    elif sslmode and str(sslmode).lower() in ("disable", "allow", "prefer"):
        ssl_ctx = None
    else:
        ssl_ctx = None if host in ("localhost", "127.0.0.1") else ssl.create_default_context()

    conn = await asyncpg.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        ssl=ssl_ctx,
        timeout=30,
    )
    try:
        val = await conn.fetchval("SELECT 1")
        assert val == 1

        rows = await conn.fetch(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema='public'
            """
        )
        names = {r[0] for r in rows}
        # Core tables should exist; 'categories' was removed in the project
        required_any = {"users", "products", "sales", "supply_orders", "financial_settings"}
        assert any(n in names for n in required_any)
    finally:
        await conn.close()


