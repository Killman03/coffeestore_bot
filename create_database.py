"""Helper script to create PostgreSQL database."""
import asyncio
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent))

try:
    from config import settings
except Exception as e:
    print(f"❌ Error loading config: {e}")
    print("Make sure .env file exists!")
    sys.exit(1)


async def create_database():
    """Create database if it doesn't exist."""
    import asyncpg
    
    print("🔧 Creating database...")
    print(f"   Database name: {settings.db_name}")
    print(f"   User: {settings.db_user}")
    
    try:
        # Connect to postgres database to create new database
        sys_conn = await asyncpg.connect(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database='postgres'  # Connect to default postgres database
        )
        
        # Check if database exists
        exists = await sys_conn.fetchval(
            'SELECT 1 FROM pg_database WHERE datname = $1',
            settings.db_name
        )
        
        if exists:
            print(f"ℹ️  Database '{settings.db_name}' already exists")
        else:
            # Create database
            await sys_conn.execute(f'CREATE DATABASE {settings.db_name}')
            print(f"✅ Database '{settings.db_name}' created successfully!")
        
        await sys_conn.close()
        
        # Test connection to new database
        print(f"\n🔧 Testing connection to '{settings.db_name}'...")
        test_conn = await asyncpg.connect(
            host=settings.db_host,
            port=settings.db_port,
            user=settings.db_user,
            password=settings.db_password,
            database=settings.db_name
        )
        print("✅ Connection successful!")
        await test_conn.close()
        
        print("\n🎉 Database setup complete!")
        print("\n📝 Next steps:")
        print("   1. alembic upgrade head")
        print("   2. python scripts/setup_db.py")
        print("   3. python main.py")
        return True
        
    except asyncpg.InvalidPasswordError:
        print(f"❌ Invalid password for user '{settings.db_user}'")
        print("\n💡 Check your .env file:")
        print("   - DB_PASSWORD must be your actual PostgreSQL password")
        print("   - Not 'your_password_here' but your REAL password")
        return False
        
    except asyncpg.PostgresConnectionError as e:
        print(f"❌ Cannot connect to PostgreSQL!")
        print(f"   Error: {e}")
        print("\n💡 Make sure PostgreSQL is running:")
        print("   Windows: Services → PostgreSQL should be Running")
        print("   Linux: sudo systemctl start postgresql")
        print("   macOS: brew services start postgresql")
        return False
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🗄️  Database Creation Script")
    print("=" * 60)
    print()
    
    success = asyncio.run(create_database())
    
    if not success:
        print("\n" + "=" * 60)
        print("❌ Database creation failed - fix the issues above")
        print("=" * 60)
        sys.exit(1)

