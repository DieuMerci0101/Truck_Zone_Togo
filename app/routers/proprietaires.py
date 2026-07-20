import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.proprietaire import ProfilProprietaire
from app.models.camion import Camion
from app.models.camion_photo import CamionPhoto
from app.models.offre import OffreRecrutement
from app.routers.auth import get_current_user
from app.schemas.proprietaire import (
    CamionCreate,
    CamionOut,
    CamionUpdate,
    OffreCreate,
    OffreOut,
    OffreUpdate,
    ProfilProprietaireOut,
    ProfilProprietaireUpdate,
)

router = APIRouter(prefix="/api/proprietaires", tags=["Propriétaires"])


def _localisation_wkt(lat: float, lng: float) -> str:
    return f"POINT({lng} {lat})"


# ─── Profil ─────────────────────────────────────────

@router.get("/", response_model=list[ProfilProprietaireOut])
async def list_proprietaires(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfilProprietaire).offset(skip).limit(limit)
    )
    return result.scalars().all()


@router.get("/me", response_model=ProfilProprietaireOut)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfilProprietaire).where(ProfilProprietaire.user_id == current_user.id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil propriétaire non trouvé")
    return profil


@router.post("/me", response_model=ProfilProprietaireOut, status_code=201)
async def create_my_profile(
    data: ProfilProprietaireUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role.value != "proprietaire":
        raise HTTPException(status_code=403, detail="Réservé aux propriétaires")

    existing = await db.execute(
        select(ProfilProprietaire).where(ProfilProprietaire.user_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Profil déjà créé")

    wkt = _localisation_wkt(
        data.localisation_lat or 0.0,
        data.localisation_lng or 0.0,
    )
    profil = ProfilProprietaire(
        id=uuid.uuid4(),
        user_id=current_user.id,
        nom_entreprise=data.nom_entreprise,
        type_activite=data.type_activite or "transport",
        adresse=data.adresse or "",
        localisation=wkt,
        bio=data.bio,
    )
    db.add(profil)
    await db.flush()
    await db.refresh(profil)
    return profil


@router.get("/{proprietaire_id}", response_model=ProfilProprietaireOut)
async def get_proprietaire(
    proprietaire_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ProfilProprietaire).where(ProfilProprietaire.id == proprietaire_id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Propriétaire non trouvé")
    return profil


@router.put("/me", response_model=ProfilProprietaireOut)
async def update_my_profile(
    data: ProfilProprietaireUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfilProprietaire).where(ProfilProprietaire.user_id == current_user.id)
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


# ─── Camions ────────────────────────────────────────

async def _get_my_profil(current_user: User, db: AsyncSession) -> ProfilProprietaire:
    result = await db.execute(
        select(ProfilProprietaire).where(ProfilProprietaire.user_id == current_user.id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil propriétaire non trouvé — créez-le d'abord")
    return profil


@router.get("/me/camions", response_model=list[CamionOut])
async def list_my_camions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(Camion).where(Camion.proprietaire_id == profil.id)
    )
    return result.scalars().all()


@router.post("/me/camions", response_model=CamionOut, status_code=201)
async def create_camion(
    data: CamionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    camion = Camion(
        id=uuid.uuid4(),
        proprietaire_id=profil.id,
        immatriculation=data.immatriculation,
        marque=data.marque,
        modele=data.modele,
        annee=data.annee,
        type_camion=data.type_camion,
        capacite_charge=data.capacite_charge,
        etat=data.etat,
        description=data.description,
    )
    db.add(camion)
    await db.flush()
    await db.refresh(camion)
    return camion


@router.get("/me/camions/{camion_id}", response_model=CamionOut)
async def get_camion(
    camion_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(Camion).where(
            Camion.id == camion_id,
            Camion.proprietaire_id == profil.id,
        )
    )
    camion = result.scalar_one_or_none()
    if not camion:
        raise HTTPException(status_code=404, detail="Camion non trouvé")
    return camion


@router.put("/me/camions/{camion_id}", response_model=CamionOut)
async def update_camion(
    camion_id: uuid.UUID,
    data: CamionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(Camion).where(
            Camion.id == camion_id,
            Camion.proprietaire_id == profil.id,
        )
    )
    camion = result.scalar_one_or_none()
    if not camion:
        raise HTTPException(status_code=404, detail="Camion non trouvé")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(camion, field, value)
    await db.flush()
    await db.refresh(camion)
    return camion


@router.delete("/me/camions/{camion_id}")
async def delete_camion(
    camion_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(Camion).where(
            Camion.id == camion_id,
            Camion.proprietaire_id == profil.id,
        )
    )
    camion = result.scalar_one_or_none()
    if not camion:
        raise HTTPException(status_code=404, detail="Camion non trouvé")
    await db.delete(camion)
    await db.flush()
    return {"message": "Camion supprimé"}


@router.post("/me/camions/{camion_id}/photos")
async def upload_camion_photo(
    camion_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(Camion).where(
            Camion.id == camion_id,
            Camion.proprietaire_id == profil.id,
        )
    )
    camion = result.scalar_one_or_none()
    if not camion:
        raise HTTPException(status_code=404, detail="Camion non trouvé")

    photo = CamionPhoto(
        id=uuid.uuid4(),
        camion_id=camion.id,
        photo_url="/uploads/placeholder.jpg",
        est_principale=False,
    )
    db.add(photo)
    await db.flush()
    return {"id": str(photo.id), "message": "Photo uploadée", "url": photo.photo_url}


@router.delete("/me/camions/{camion_id}/photos/{photo_id}")
async def delete_camion_photo(
    camion_id: uuid.UUID,
    photo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(CamionPhoto).where(
            CamionPhoto.id == photo_id,
            CamionPhoto.camion_id == camion_id,
        )
    )
    photo = result.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo non trouvée")
    await db.delete(photo)
    await db.flush()
    return {"message": "Photo supprimée"}


# ─── Offres ─────────────────────────────────────────

@router.get("/me/offres", response_model=list[OffreOut])
async def list_my_offres(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(OffreRecrutement).where(OffreRecrutement.proprietaire_id == profil.id)
    )
    offres = result.scalars().all()
    out = []
    for o in offres:
        out.append(OffreOut(
            id=o.id,
            proprietaire_id=uuid.UUID(o.proprietaire_id) if isinstance(o.proprietaire_id, str) else o.proprietaire_id,
            titre=o.titre,
            description=o.description,
            type_contrat=o.type_contrat.value if hasattr(o.type_contrat, 'value') else o.type_contrat,
            salaire_propose=o.salaire_propose,
            zone_travail=o.zone_travail,
            date_debut=str(o.date_debut),
            camion_id=uuid.UUID(o.camion_id) if o.camion_id and isinstance(o.camion_id, str) else o.camion_id,
            statut=o.statut.value if hasattr(o.statut, 'value') else o.statut,
            created_at=o.created_at,
        ))
    return out


@router.post("/me/offres", response_model=OffreOut, status_code=201)
async def create_offre(
    data: OffreCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    from datetime import date as date_type
    offre = OffreRecrutement(
        id=uuid.uuid4(),
        proprietaire_id=profil.id,
        titre=data.titre,
        description=data.description,
        type_contrat=data.type_contrat,
        salaire_propose=data.salaire_propose,
        zone_travail=data.zone_travail,
        date_debut=date_type.fromisoformat(data.date_debut),
        camion_id=str(data.camion_id) if data.camion_id else None,
    )
    db.add(offre)
    await db.flush()
    await db.refresh(offre)
    return OffreOut(
        id=offre.id,
        proprietaire_id=offre.proprietaire_id,
        titre=offre.titre,
        description=offre.description,
        type_contrat=offre.type_contrat.value if hasattr(offre.type_contrat, 'value') else offre.type_contrat,
        salaire_propose=offre.salaire_propose,
        zone_travail=offre.zone_travail,
        date_debut=str(offre.date_debut),
        camion_id=offre.camion_id,
        statut=offre.statut.value if hasattr(offre.statut, 'value') else offre.statut,
        created_at=offre.created_at,
    )


@router.get("/me/offres/{offre_id}", response_model=OffreOut)
async def get_offre(
    offre_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(OffreRecrutement).where(
            OffreRecrutement.id == offre_id,
            OffreRecrutement.proprietaire_id == profil.id,
        )
    )
    offre = result.scalar_one_or_none()
    if not offre:
        raise HTTPException(status_code=404, detail="Offre non trouvée")
    return OffreOut(
        id=offre.id,
        proprietaire_id=offre.proprietaire_id,
        titre=offre.titre,
        description=offre.description,
        type_contrat=offre.type_contrat.value if hasattr(offre.type_contrat, 'value') else offre.type_contrat,
        salaire_propose=offre.salaire_propose,
        zone_travail=offre.zone_travail,
        date_debut=str(offre.date_debut),
        camion_id=offre.camion_id,
        statut=offre.statut.value if hasattr(offre.statut, 'value') else offre.statut,
        created_at=offre.created_at,
    )


@router.put("/me/offres/{offre_id}", response_model=OffreOut)
async def update_offre(
    offre_id: uuid.UUID,
    data: OffreUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(OffreRecrutement).where(
            OffreRecrutement.id == offre_id,
            OffreRecrutement.proprietaire_id == profil.id,
        )
    )
    offre = result.scalar_one_or_none()
    if not offre:
        raise HTTPException(status_code=404, detail="Offre non trouvée")

    update_data = data.model_dump(exclude_unset=True)
    if "date_debut" in update_data:
        from datetime import date as date_type
        update_data["date_debut"] = date_type.fromisoformat(update_data["date_debut"])
    for field, value in update_data.items():
        setattr(offre, field, value)
    await db.flush()
    await db.refresh(offre)
    return OffreOut(
        id=offre.id,
        proprietaire_id=offre.proprietaire_id,
        titre=offre.titre,
        description=offre.description,
        type_contrat=offre.type_contrat.value if hasattr(offre.type_contrat, 'value') else offre.type_contrat,
        salaire_propose=offre.salaire_propose,
        zone_travail=offre.zone_travail,
        date_debut=str(offre.date_debut),
        camion_id=offre.camion_id,
        statut=offre.statut.value if hasattr(offre.statut, 'value') else offre.statut,
        created_at=offre.created_at,
    )


@router.delete("/me/offres/{offre_id}")
async def delete_offre(
    offre_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(OffreRecrutement).where(
            OffreRecrutement.id == offre_id,
            OffreRecrutement.proprietaire_id == profil.id,
        )
    )
    offre = result.scalar_one_or_none()
    if not offre:
        raise HTTPException(status_code=404, detail="Offre non trouvée")
    await db.delete(offre)
    await db.flush()
    return {"message": "Offre supprimée"}
