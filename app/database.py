from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine # type: ignore
from sqlalchemy.orm import DeclarativeBase # type: ignore

from app.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.database_url_async,
    echo=True,
    pool_size=10,
    max_overflow=20,
)

async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Dependency FastAPI pour obtenir une session DB."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Crée toutes les tables (pour dev uniquement)."""
    from app.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Ferme la connexion DB."""
    await engine.dispose()
