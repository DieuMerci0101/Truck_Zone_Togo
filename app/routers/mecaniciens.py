import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.mecanicien import ProfilMecanicien
from app.models.assistance import DemandeAssistance
from app.routers.auth import get_current_user
from app.schemas.mecanicien import (
    AssistanceCreate,
    AssistanceOut,
    AssistanceUpdateStatut,
    ProfilMecanicienOut,
    ProfilMecanicienUpdate,
)

router = APIRouter(prefix="/api/mecaniciens", tags=["Mécaniciens"])


def _localisation_wkt(lat: float, lng: float) -> str:
    return f"POINT({lng} {lat})"


def _assistance_out(a: DemandeAssistance) -> AssistanceOut:
    return AssistanceOut(
        id=a.id,
        demandeur_id=a.demandeur_id,
        mecanicien_id=a.mecanicien_id,
        type_panne=a.type_panne.value if hasattr(a.type_panne, "value") else a.type_panne,
        description=a.description,
        urgence=a.urgence.value if hasattr(a.urgence, "value") else a.urgence,
        vehicule_description=a.vehicule_description,
        statut=a.statut.value if hasattr(a.statut, "value") else a.statut,
        created_at=a.created_at,
    )


@router.get("/", response_model=list[ProfilMecanicienOut])
async def list_mecaniciens(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    specialite: str | None = None,
    disponibilite: str | None = None,
    tarification: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ProfilMecanicien)
    if specialite:
        query = query.where(ProfilMecanicien.specialites.any(specialite))
    if disponibilite:
        query = query.where(ProfilMecanicien.disponibilite == disponibilite)
    if tarification:
        query = query.where(ProfilMecanicien.tarification == tarification)
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/me", response_model=ProfilMecanicienOut)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfilMecanicien).where(ProfilMecanicien.user_id == current_user.id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil mécanicien non trouvé")
    return profil


@router.post("/me", response_model=ProfilMecanicienOut, status_code=201)
async def create_my_profile(
    data: ProfilMecanicienUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role.value != "mecanicien":
        raise HTTPException(status_code=403, detail="Réservé aux mécaniciens")
    existing = await db.execute(
        select(ProfilMecanicien).where(ProfilMecanicien.user_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Profil déjà créé")

    wkt = _localisation_wkt(
        data.localisation_lat or 0.0,
        data.localisation_lng or 0.0,
    )
    profil = ProfilMecanicien(
        id=uuid.uuid4(),
        user_id=current_user.id,
        specialites=data.specialites or [],
        annees_experience=data.annees_experience or 0,
        certifications=data.certifications,
        tarification=data.tarification or "Payant",
        localisation=wkt,
        rayon_intervention=data.rayon_intervention or 30,
        bio=data.bio,
    )
    db.add(profil)
    await db.flush()
    await db.refresh(profil)
    return profil


@router.put("/me", response_model=ProfilMecanicienOut)
async def update_my_profile(
    data: ProfilMecanicienUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfilMecanicien).where(ProfilMecanicien.user_id == current_user.id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil non trouvé")

    update_data = data.model_dump(exclude_unset=True)
    if "localisation_lat" in update_data or "localisation_lng" in update_data:
        lat = update_data.pop("localisation_lat", None) or 0.0
        lng = update_data.pop("localisation_lng", None) or 0.0
        profil.localisation = _localisation_wkt(lat, lng)
    for field, value in update_data.items():
        if hasattr(profil, field):
            setattr(profil, field, value)
    await db.flush()
    await db.refresh(profil)
    return profil


@router.get("/proches", response_model=list[ProfilMecanicienOut])
async def get_mecaniciens_proches(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    rayon_km: int = Query(50, gt=0),
    specialite: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ProfilMecanicien).where(
        ProfilMecanicien.disponibilite == "disponible"
    )
    if specialite:
        query = query.where(ProfilMecanicien.specialites.any(specialite))
    result = await db.execute(query.limit(50))
    return result.scalars().all()


@router.get("/{mecanicien_id}", response_model=ProfilMecanicienOut)
async def get_mecanicien(
    mecanicien_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ProfilMecanicien).where(ProfilMecanicien.id == mecanicien_id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Mécanicien non trouvé")
    return profil


# ─── Assistance ─────────────────────────────────────

@router.post("/assistance", response_model=AssistanceOut, status_code=201)
async def create_assistance(
    data: AssistanceCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wkt = _localisation_wkt(data.localisation_lat, data.localisation_lng)
    assistance = DemandeAssistance(
        id=uuid.uuid4(),
        demandeur_id=current_user.id,
        type_panne=data.type_panne,
        description=data.description,
        urgence=data.urgence,
        localisation=wkt,
        vehicule_description=data.vehicule_description,
    )
    db.add(assistance)
    await db.flush()
    await db.refresh(assistance)
    return _assistance_out(assistance)


@router.get("/assistance/{assistance_id}", response_model=AssistanceOut)
async def get_assistance(
    assistance_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DemandeAssistance).where(DemandeAssistance.id == assistance_id)
    )
    assistance = result.scalar_one_or_none()
    if not assistance:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    return _assistance_out(assistance)


@router.get("/assistance/mes-demandes", response_model=list[AssistanceOut])
async def list_my_assistance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DemandeAssistance)
        .where(DemandeAssistance.demandeur_id == current_user.id)
        .order_by(DemandeAssistance.created_at.desc())
    )
    return [_assistance_out(a) for a in result.scalars().all()]


@router.put("/assistance/{assistance_id}/statut")
async def update_assistance_statut(
    assistance_id: uuid.UUID,
    data: AssistanceUpdateStatut,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DemandeAssistance).where(DemandeAssistance.id == assistance_id)
    )
    assistance = result.scalar_one_or_none()
    if not assistance:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    assistance.statut = data.statut
    await db.flush()
    return {"message": "Statut mis à jour", "statut": assistance.statut}
