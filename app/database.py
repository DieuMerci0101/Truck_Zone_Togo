from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()


engine = create_async_engine(
    settings.database_url_async,
    echo=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)


async_session = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dépendance FastAPI pour obtenir une session de base de données.
    """
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    from app.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with engine.begin() as conn:
        from sqlalchemy import text
        for stmt in [
            "ALTER TABLE messages ADD COLUMN IF NOT EXISTS media_url VARCHAR(500)",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass


async def close_db():
    await engine.dispose()