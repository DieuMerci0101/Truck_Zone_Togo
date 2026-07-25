import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.chauffeur import ProfilChauffeur
from app.models.camion import Camion
from app.models.camion_photo import CamionPhoto
from app.models.document import Document
from app.routers.auth import get_current_user
from app.schemas.chauffeur import (
    DisponibiliteUpdate,
    ProfilChauffeurCreate,
    ProfilChauffeurOut,
    ProfilChauffeurUpdate,
)
from app.schemas.proprietaire import CamionCreate, CamionOut, CamionUpdate, CamionPhotoOut

router = APIRouter(prefix="/api/chauffeurs", tags=["Chauffeurs"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "camions")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_PHOTOS_PER_CAMION = 10


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


# ─── Camions (chauffeur = propriétaire de camion) ────

async def _get_my_chauffeur_profile(current_user: User, db: AsyncSession) -> ProfilChauffeur:
    result = await db.execute(
        select(ProfilChauffeur).where(ProfilChauffeur.user_id == current_user.id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil chauffeur non trouvé — créez-le d'abord")
    return profil


async def _verify_chauffeur_camion(current_user: User, camion_id: uuid.UUID, db: AsyncSession) -> Camion:
    profil = await _get_my_chauffeur_profile(current_user, db)
    result = await db.execute(
        select(Camion).where(Camion.id == camion_id, Camion.chauffeur_id == profil.id)
    )
    camion = result.scalar_one_or_none()
    if not camion:
        raise HTTPException(status_code=404, detail="Camion non trouvé")
    return camion


@router.get("/me/camions", response_model=list[CamionOut])
async def list_my_camions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_chauffeur_profile(current_user, db)
    result = await db.execute(
        select(Camion).where(Camion.chauffeur_id == profil.id)
    )
    return result.scalars().all()


@router.post("/me/camions", response_model=CamionOut, status_code=201)
async def create_camion(
    data: CamionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_chauffeur_profile(current_user, db)
    camion = Camion(
        id=uuid.uuid4(),
        chauffeur_id=profil.id,
        immatriculation=data.immatriculation,
        marque=data.marque,
        modele=data.modele,
        annee=data.annee,
        type_camion=data.type_camion,
        capacite_charge=data.capacite_charge,
        etat=data.etat,
        description=data.description,
        is_public=data.is_public,
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
    camion = await _verify_chauffeur_camion(current_user, camion_id, db)
    return camion


@router.put("/me/camions/{camion_id}", response_model=CamionOut)
async def update_camion(
    camion_id: uuid.UUID,
    data: CamionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    camion = await _verify_chauffeur_camion(current_user, camion_id, db)
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
    camion = await _verify_chauffeur_camion(current_user, camion_id, db)
    await db.delete(camion)
    await db.flush()
    return {"message": "Camion supprimé"}


@router.post("/me/camions/{camion_id}/photos")
async def upload_camion_photo(
    camion_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    camion = await _verify_chauffeur_camion(current_user, camion_id, db)

    existing = await db.execute(
        select(CamionPhoto).where(CamionPhoto.camion_id == camion.id)
    )
    count = len(existing.scalars().all())
    if count >= MAX_PHOTOS_PER_CAMION:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_PHOTOS_PER_CAMION} photos par camion")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Format non supporté (JPG, PNG, WebP uniquement)")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Le fichier ne doit pas dépasser 5 Mo")

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    is_first = count == 0
    photo = CamionPhoto(
        id=uuid.uuid4(),
        camion_id=camion.id,
        photo_url=f"/uploads/camions/{filename}",
        est_principale=is_first,
    )
    db.add(photo)

    if is_first:
        camion.photo_principale_url = photo.photo_url

    await db.flush()
    return {"id": str(photo.id), "message": "Photo uploadée", "url": photo.photo_url, "est_principale": is_first}


@router.delete("/me/camions/{camion_id}/photos/{photo_id}")
async def delete_camion_photo(
    camion_id: uuid.UUID,
    photo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    camion = await _verify_chauffeur_camion(current_user, camion_id, db)
    result = await db.execute(
        select(CamionPhoto).where(CamionPhoto.id == photo_id, CamionPhoto.camion_id == camion_id)
    )
    photo = result.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo non trouvée")

    if photo.photo_url and photo.photo_url.startswith("/uploads/"):
        file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), photo.photo_url.lstrip("/"))
        if os.path.exists(file_path):
            os.remove(file_path)

    was_main = photo.est_principale
    await db.delete(photo)
    await db.flush()

    if was_main:
        next_photo = await db.execute(
            select(CamionPhoto)
            .where(CamionPhoto.camion_id == camion_id)
            .order_by(CamionPhoto.created_at)
            .limit(1)
        )
        next_p = next_photo.scalar_one_or_none()
        if next_p:
            next_p.est_principale = True
            camion.photo_principale_url = next_p.photo_url
        else:
            camion.photo_principale_url = None
        await db.flush()

    return {"message": "Photo supprimée"}


@router.post("/me/camions/{camion_id}/photos/{photo_id}/principale")
async def set_main_photo(
    camion_id: uuid.UUID,
    photo_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    camion = await _verify_chauffeur_camion(current_user, camion_id, db)
    result = await db.execute(
        select(CamionPhoto).where(CamionPhoto.id == photo_id, CamionPhoto.camion_id == camion_id)
    )
    photo = result.scalar_one_or_none()
    if not photo:
        raise HTTPException(status_code=404, detail="Photo non trouvée")

    all_photos = await db.execute(
        select(CamionPhoto).where(CamionPhoto.camion_id == camion_id)
    )
    for p in all_photos.scalars():
        p.est_principale = False

    photo.est_principale = True
    camion.photo_principale_url = photo.photo_url
    await db.flush()
    return {"message": "Photo principale mise à jour"}


@router.post("/me/camions/{camion_id}/publish")
async def toggle_publish_camion(
    camion_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    camion = await _verify_chauffeur_camion(current_user, camion_id, db)
    camion.is_public = not camion.is_public
    await db.flush()
    return {"message": f"Camion {'publié' if camion.is_public else 'dépublié'}", "is_public": camion.is_public}
