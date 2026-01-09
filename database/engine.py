from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
from typing import AsyncGenerator

from config import settings
from database.models import Base


# Create async engine
engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,  # Test connections before using them
    pool_size=10,  # Number of connections to maintain in the pool
    max_overflow=20,  # Maximum overflow connections
    pool_recycle=3600,  # Recycle connections after 1 hour (prevents stale connections)
    pool_timeout=30,  # Wait up to 30 seconds for a connection from the pool
    connect_args={
        "timeout": 60,  # Connection timeout
        "command_timeout": 60,  # Command timeout
        "server_settings": {
            "application_name": "coffeestore_bot",
            "jit": "off",  # Disable JIT compilation for better stability
        }
    }
)

# Create session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,  # Don't expire objects after commit
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database - create all tables."""
    async with engine.begin() as conn:
        # Create tables if they don't exist
        await conn.run_sync(Base.metadata.create_all)
        # Ensure users.telegram_id is BIGINT (in case migrations weren't run)
        try:
            result = await conn.execute(text(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'users'
                  AND column_name = 'telegram_id'
                """
            ))
            row = result.first()
            if row and str(row[0]).lower() != 'bigint':
                await conn.execute(text(
                    "ALTER TABLE users ALTER COLUMN telegram_id TYPE BIGINT USING telegram_id::bigint"
                ))
        except Exception:
            # Best-effort; defer to Alembic if this fails
            pass

        # Safety: remove legacy categories schema if still present
        try:
            # Drop products.category_id if it still exists
            await conn.execute(text(
                "ALTER TABLE IF EXISTS products DROP COLUMN IF EXISTS category_id"
            ))
            # Drop categories table if present
            await conn.execute(text(
                "DROP TABLE IF EXISTS categories CASCADE"
            ))
        except Exception:
            # Ignore if already aligned or insufficient permissions; handled by migrations otherwise
            pass

        # Add default_sale_price if missing
        try:
            await conn.execute(text(
                "ALTER TABLE IF EXISTS products ADD COLUMN IF NOT EXISTS default_sale_price NUMERIC(10,2)"
            ))
        except Exception:
            pass


async def dispose_db():
    """Dispose database engine and close all connections."""
    await engine.dispose()

