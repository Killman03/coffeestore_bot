"""Script to initialize database and create initial data."""
import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent))

from database import init_db
from database.engine import async_session_maker
from services.financial_service import FinancialService


async def setup_database():
    """Setup database with initial data."""
    print("🔧 Initializing database...")
    
    # Create tables
    await init_db()
    print("✅ Database tables created!")
    
    # Create default financial settings
    async with async_session_maker() as session:
        print("\n💵 Creating default financial settings...")
        financial_settings = await FinancialService.get_or_create_default_settings(session)
        print(f"✅ Financial settings created:")
        print(f"   - CNY Rate: {financial_settings.cny_to_som_rate}")
        print(f"   - Delivery cost: {financial_settings.delivery_cost_per_kg} som/kg")
    
    print("\n🎉 Database setup completed successfully!")
    print("\n📝 Next steps:")
    print("   1. Start the bot: python main.py")
    print("   2. Open Telegram and send /start to your bot")
    print("   3. Add your first product: /add_product")


if __name__ == "__main__":
    try:
        asyncio.run(setup_database())
    except Exception as e:
        print(f"\n❌ Error during setup: {e}")
        sys.exit(1)

