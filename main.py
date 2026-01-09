import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from database import init_db, dispose_db
from bot.middlewares import DatabaseMiddleware, UserMiddleware
from bot.handlers import common, products, supply, sales, finance, reports

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def init_database_with_retry(max_retries: int = 5, retry_delay: int = 3):
    """Initialize database with retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Initializing database (attempt {attempt}/{max_retries})...")
            await init_db()
            logger.info("Database initialized successfully!")
            return True
        except Exception as e:
            logger.error(f"Database initialization failed (attempt {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
            else:
                logger.error("Max retries reached. Could not initialize database.")
                raise


async def main():
    """Main bot function."""
    # Initialize bot and dispatcher
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher()
    
    # Register middlewares
    dp.message.middleware(DatabaseMiddleware())
    dp.callback_query.middleware(DatabaseMiddleware())
    dp.message.middleware(UserMiddleware())
    
    # Register routers
    dp.include_router(common.router)
    dp.include_router(products.router)
    dp.include_router(supply.router)
    dp.include_router(sales.router)
    dp.include_router(finance.router)
    dp.include_router(reports.router)
    
    # Initialize database with retry logic
    await init_database_with_retry()
    
    # Start polling
    logger.info("Starting bot...")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        logger.info("Shutting down bot...")
        await bot.session.close()
        await dispose_db()
        logger.info("Database connections closed")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")

