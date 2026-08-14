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
            "ALTER TYPE etat_camion ADD VALUE IF NOT EXISTS 'bon_etat'",
            "ALTER TYPE statut_assistance ADD VALUE IF NOT EXISTS 'pris_en_charge'",
            "ALTER TABLE profils_mecanicien ADD COLUMN IF NOT EXISTS proof_document_url VARCHAR(500)",
            "ALTER TABLE profils_mecanicien ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50) DEFAULT 'pending_upload'",
            "ALTER TABLE profils_mecanicien ADD COLUMN IF NOT EXISTS position_active BOOLEAN DEFAULT false",
            "ALTER TABLE profils_mecanicien ADD COLUMN IF NOT EXISTS position_updated_at TIMESTAMPTZ",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_status VARCHAR(50) DEFAULT 'pending_upload'",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_reject_motif TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS country_id UUID REFERENCES countries(id) ON DELETE SET NULL",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS photo_profil_version INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE notifications ADD COLUMN IF NOT EXISTS metadata_json TEXT",
            "ALTER TABLE demandes_assistance ADD COLUMN IF NOT EXISTS pris_en_charge_at TIMESTAMPTZ",
            "ALTER TYPE type_document ADD VALUE IF NOT EXISTS 'passeport'",
            "ALTER TYPE type_document ADD VALUE IF NOT EXISTS 'rccm'",
            "ALTER TYPE type_document ADD VALUE IF NOT EXISTS 'patente'",
            "ALTER TYPE type_document ADD VALUE IF NOT EXISTS 'casier'",
            "ALTER TYPE type_document ADD VALUE IF NOT EXISTS 'diplome'",
            "ALTER TYPE type_document ADD VALUE IF NOT EXISTS 'photo_identite'",
        ]:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass


async def close_db():
    await engine.dispose()