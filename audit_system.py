import sys
import asyncio
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from src.core.config import get_settings
from src.core.cache import CacheService

async def check_redis(settings):
    try:
        cache = CacheService()
        await cache.connect()
        if cache.is_connected:
            return "Redis Connected successfully."
        return "Redis connection failed (maybe not running?)."
    except Exception as e:
        return f"Redis Error: {e}"

def check_postgres(settings):
    try:
        engine = create_engine(settings.database_url)
        with engine.connect() as conn:
            # Check tables
            result = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';"))
            tables = [row[0] for row in result]
            if tables:
                return f"Postgres Connected. Tables: {', '.join(tables)}"
            else:
                return "Postgres Connected. No tables found (needs migrations)."
    except Exception as e:
        return f"Postgres Error: {e}"

def check_frontend():
    import pathlib
    fe_path = pathlib.Path('marketpulse-client')
    if not fe_path.exists():
        return "Frontend missing."
    
    pkg_json = fe_path / 'package.json'
    if not pkg_json.exists():
        return "package.json missing."
    
    return "Frontend directory exists with package.json."

async def main():
    print("Starting MarketPulse Deep Audit...")
    settings = get_settings()
    print("\n--- DATABASE ---")
    print(check_postgres(settings))
    
    print("\n--- CACHE ---")
    print(await check_redis(settings))
    
    print("\n--- FRONTEND ---")
    print(check_frontend())
    
    print("\n--- API MODULES ---")
    try:
        from src.api.main import app
        print(f"FastAPI app loaded. {len(app.routes)} routes configured.")
    except Exception as e:
        print(f"Error loading FastAPI app: {e}")

    print("\n--- DATA COLLECTOR ---")
    try:
        from src.data.market_collector import MarketPulseCollector
        print("MarketPulseCollector loaded successfully.")
    except ImportError as e:
        print(f"MarketPulseCollector module not found: {e}")
    except Exception as e:
        print(f"MarketPulseCollector initialization error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
