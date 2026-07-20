"""
Script pour initialiser la base de données.
Usage: python -m app.init_db
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, init_db
from app.models import Base


async def main():
    print("🔧 Création des tables dans PostgreSQL...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Tables créées avec succès !")
    print(f"📊 Tables créées : {list(Base.metadata.tables.keys())}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
