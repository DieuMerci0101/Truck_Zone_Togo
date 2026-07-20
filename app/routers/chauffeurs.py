import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.chauffeur import ProfilChauffeur
from app.models.document import Document
from app.routers.auth import get_current_user
from app.schemas.chauffeur import (
    DisponibiliteUpdate,
    ProfilChauffeurCreate,
    ProfilChauffeurOut,
    ProfilChauffeurUpdate,
)

router = APIRouter(prefix="/api/chauffeurs", tags=["Chauffeurs"])


@router.get("/", response_model=list[ProfilChauffeurOut])
async def list_chauffeurs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    disponibilite: str | None = None,
    categorie_permis: str | None = None,
    experience_min: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ProfilChauffeur)
    if disponibilite:
        query = query.where(ProfilChauffeur.disponibilite == disponibilite)
    if categorie_permis:
        query = query.where(ProfilChauffeur.categorie_permis == categorie_permis)
    if experience_min:
        query = query.where(ProfilChauffeur.annees_experience >= experience_min)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/me", response_model=ProfilChauffeurOut)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfilChauffeur).where(ProfilChauffeur.user_id == current_user.id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil chauffeur non trouvé")
    return profil


@router.post("/me", response_model=ProfilChauffeurOut, status_code=201)
async def create_my_profile(
    data: ProfilChauffeurCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role.value != "chauffeur":
        raise HTTPException(status_code=403, detail="Réservé aux chauffeurs")

    existing = await db.execute(
        select(ProfilChauffeur).where(ProfilChauffeur.user_id == current_user.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Profil déjà créé")

    profil = ProfilChauffeur(
        id=uuid.uuid4(),
        user_id=current_user.id,
        numero_permis=data.numero_permis,
        categorie_permis=data.categorie_permis,
        annees_experience=data.annees_experience,
        types_transport=data.types_transport,
        zones_circulation=data.zones_circulation,
        disponibilite=data.disponibilite,
        bio=data.bio,
    )
    db.add(profil)
    await db.flush()
    await db.refresh(profil)
    return profil


@router.get("/{chauffeur_id}", response_model=ProfilChauffeurOut)
async def get_chauffeur(chauffeur_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ProfilChauffeur).where(ProfilChauffeur.id == chauffeur_id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Chauffeur non trouvé")
    return profil


@router.put("/me", response_model=ProfilChauffeurOut)
async def update_my_profile(
    data: ProfilChauffeurUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfilChauffeur).where(ProfilChauffeur.user_id == current_user.id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil non trouvé")

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profil, field, value)
    await db.flush()
    await db.refresh(profil)
    return profil


@router.put("/me/statut")
async def update_disponibilite(
    data: DisponibiliteUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfilChauffeur).where(ProfilChauffeur.user_id == current_user.id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil non trouvé")

    profil.disponibilite = data.disponibilite
    await db.flush()
    return {"message": "Disponibilité mise à jour", "disponibilite": profil.disponibilite}


@router.post("/me/documents", status_code=201)
async def upload_document(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    doc = Document(
        id=uuid.uuid4(),
        utilisateur_id=current_user.id,
        type_document="permis",
        fichier_url="/uploads/placeholder.pdf",
        statut="en_attente",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)
    return {"id": str(doc.id), "message": "Document uploadé"}


@router.get("/me/documents")
async def list_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.utilisateur_id == current_user.id)
    )
    docs = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "type_document": d.type_document.value if hasattr(d.type_document, 'value') else d.type_document,
            "fichier_url": d.fichier_url,
            "statut": d.statut.value if hasattr(d.statut, 'value') else d.statut,
            "created_at": d.created_at.isoformat(),
        }
        for d in docs
    ]
