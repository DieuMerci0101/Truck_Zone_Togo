from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.country import Country

router = APIRouter(prefix="/api/countries", tags=["Countries"])


@router.get("")
async def list_countries(db: AsyncSession = Depends(get_db)):
    """
    Retourne la liste des pays actifs (ordonnée par nom), avec leur indicatif
    téléphonique E.164 et leur drapeau. Utilisé par le sélecteur de pays du
    formulaire d'inscription.
    """
    result = await db.execute(
        select(Country)
        .where(Country.is_active.is_(True))
        .order_by(Country.sort_order.asc(), Country.name.asc())
    )
    countries = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "code": c.code,
            "phone_code": c.phone_code,
            "flag_emoji": c.flag_emoji,
            "is_active": c.is_active,
        }
        for c in countries
    ]
