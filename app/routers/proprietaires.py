import os
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.user import User
from app.models.proprietaire import ProfilProprietaire
from app.models.camion import Camion
from app.models.camion_photo import CamionPhoto
from app.models.offre import OffreRecrutement
from app.models.assistance import DemandeAssistance
from app.models.conversation import Conversation, ConversationParticipant
from app.models.document import Document
from app.models.enums import TypeDocument
from app.routers.auth import get_current_user, require_verified
from app.schemas.proprietaire import (
    CamionCreate,
    CamionOut,
    CamionPhotoOut,
    CamionProlonger,
    CamionUpdate,
    OffreCreate,
    OffreOut,
    OffreUpdate,
    ProfilProprietaireOut,
    ProfilProprietaireUpdate,
)
from app.schemas.mecanicien import AssistanceCreate, AssistanceOut

router = APIRouter(prefix="/api/proprietaires", tags=["Propriétaires"])

EDIT_WINDOW_MINUTES = 5
OFFRE_EXPIRATION_DAYS = 30

ETATS_PUBLIABLES = {"bon_etat", "excellent"}


def _valider_publication(etat: str, is_public: bool, expires_at: datetime | None = None) -> None:
    """Valide les règles métier de publication d'un camion."""
    if is_public and etat in ("en_reparation", "use"):
        raise HTTPException(
            status_code=400,
            detail="Impossible de publier un camion en réparation ou usé. Il doit être en bon état.",
        )
    if is_public and etat in ETATS_PUBLIABLES:
        if expires_at is None:
            raise HTTPException(
                status_code=400,
                detail="Un camion publié doit avoir une date d'expiration.",
            )
        if isinstance(expires_at, str):
            try:
                expires_at = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail="Format de date d'expiration invalide")
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            raise HTTPException(
                status_code=400,
                detail="La date d'expiration doit être dans le futur.",
            )

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "camions")
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
MAX_PHOTOS_PER_CAMION = 10


def _localisation_wkt(lat: float, lng: float) -> str:
    return f"POINT({lng} {lat})"


def _is_editable(created_at) -> bool:
    if not created_at:
        return False
    now = datetime.now(timezone.utc)
    created = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at
    return (now - created) <= timedelta(minutes=EDIT_WINDOW_MINUTES)


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
        profil = ProfilProprietaire(
            user_id=current_user.id,
            type_activite="transport",
            adresse="",
        )
        db.add(profil)
        await db.flush()
        await db.refresh(profil)
    return profil


@router.get("/me/camions", response_model=list[CamionOut])
async def list_my_camions(
    current_user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(Camion)
        .options(
            selectinload(Camion.photos),
            selectinload(Camion.proprietaire).selectinload(ProfilProprietaire.user),
        )
        .where(Camion.proprietaire_id == profil.id)
    )
    return result.scalars().all()


@router.post("/me/camions", response_model=CamionOut, status_code=201)
async def create_camion(
    data: CamionCreate,
    current_user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_db),
):
    _valider_publication(data.etat, data.is_public, data.expires_at)

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
        is_public=data.is_public,
        expires_at=data.expires_at,
    )
    db.add(camion)
    await db.flush()
    await db.refresh(camion)

    result = await db.execute(
        select(Camion)
        .options(
            selectinload(Camion.photos),
            selectinload(Camion.proprietaire).selectinload(ProfilProprietaire.user),
        )
        .where(Camion.id == camion.id)
    )
    camion = result.scalar_one()
    return camion


@router.get("/me/camions/{camion_id}", response_model=CamionOut)
async def get_camion(
    camion_id: uuid.UUID,
    current_user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(Camion)
        .options(
            selectinload(Camion.photos),
            selectinload(Camion.proprietaire).selectinload(ProfilProprietaire.user),
        )
        .where(
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
    current_user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(Camion)
        .options(selectinload(Camion.photos))
        .where(
            Camion.id == camion_id,
            Camion.proprietaire_id == profil.id,
        )
    )
    camion = result.scalar_one_or_none()
    if not camion:
        raise HTTPException(status_code=404, detail="Camion non trouvé")

    update_data = data.model_dump(exclude_unset=True)
    new_etat = update_data.get("etat", camion.etat)
    new_is_public = update_data.get("is_public", camion.is_public)

    if new_is_public and new_etat in ("en_reparation", "use"):
        raise HTTPException(
            status_code=400,
            detail="Action interdite : Seuls les véhicules en bon ou excellent état peuvent être publiés.",
        )

    if camion.is_public and "etat" in update_data and new_etat in ("en_reparation", "use"):
        update_data["is_public"] = False
        update_data["expires_at"] = None
        new_is_public = False

    if new_is_public and new_etat in ETATS_PUBLIABLES:
        new_expires_at = update_data.get("expires_at", camion.expires_at)
        if new_expires_at is None:
            raise HTTPException(status_code=400, detail="Un camion publié doit avoir une date d'expiration.")
        if isinstance(new_expires_at, str):
            try:
                new_expires_at = datetime.fromisoformat(new_expires_at.replace("Z", "+00:00"))
            except ValueError:
                raise HTTPException(status_code=400, detail="Format de date d'expiration invalide")
        if new_expires_at.tzinfo is None:
            new_expires_at = new_expires_at.replace(tzinfo=timezone.utc)
        if new_expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="La date d'expiration doit être dans le futur.")
        update_data["expires_at"] = new_expires_at

    for field, value in update_data.items():
        setattr(camion, field, value)
    await db.flush()
    await db.refresh(camion)

    result = await db.execute(
        select(Camion)
        .options(
            selectinload(Camion.photos),
            selectinload(Camion.proprietaire).selectinload(ProfilProprietaire.user),
        )
        .where(Camion.id == camion.id)
    )
    camion = result.scalar_one()
    return camion


@router.delete("/me/camions/{camion_id}")
async def delete_camion(
    camion_id: uuid.UUID,
    current_user: User = Depends(require_verified),
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
    file: UploadFile = File(...),
    current_user: User = Depends(require_verified),
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
    current_user: User = Depends(require_verified),
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

    if photo.photo_url and photo.photo_url.startswith("/uploads/"):
        file_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), photo.photo_url.lstrip("/"))
        if os.path.exists(file_path):
            os.remove(file_path)

    was_main = photo.est_principale
    await db.delete(photo)
    await db.flush()

    if was_main:
        camion_result = await db.execute(
            select(Camion).where(Camion.id == camion_id)
        )
        camion = camion_result.scalar_one_or_none()
        if camion:
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
    current_user: User = Depends(require_verified),
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

    all_photos = await db.execute(
        select(CamionPhoto).where(CamionPhoto.camion_id == camion_id)
    )
    for p in all_photos.scalars():
        p.est_principale = False

    photo.est_principale = True

    camion_result = await db.execute(
        select(Camion).where(Camion.id == camion_id)
    )
    camion = camion_result.scalar_one_or_none()
    if camion:
        camion.photo_principale_url = photo.photo_url
    await db.flush()
    return {"message": "Photo principale mise à jour"}


class PublishCamionRequest(BaseModel):
    expires_at: str | None = None


@router.post("/me/camions/{camion_id}/publish")
async def toggle_publish_camion(
    camion_id: uuid.UUID,
    body: PublishCamionRequest,
    current_user: User = Depends(require_verified),
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

    if not camion.is_public and camion.etat in ("en_reparation", "use"):
        raise HTTPException(status_code=400, detail="Impossible de publier un camion en réparation ou usé")

    if body.expires_at and not camion.is_public:
        try:
            expires = datetime.fromisoformat(body.expires_at)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="Format de date d'expiration invalide")
        now = datetime.now(timezone.utc)
        if expires <= now:
            raise HTTPException(status_code=400, detail="La date d'expiration doit être dans le futur")
        camion.expires_at = expires

    camion.is_public = not camion.is_public
    await db.flush()
    return {"message": f"Camion {'publié' if camion.is_public else 'dépublié'}", "is_public": camion.is_public}


@router.patch("/me/camions/{camion_id}/prolonger", response_model=CamionOut)
async def prolonger_publication_camion(
    camion_id: uuid.UUID,
    data: CamionProlonger,
    current_user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    result = await db.execute(
        select(Camion)
        .options(
            selectinload(Camion.photos),
            selectinload(Camion.proprietaire).selectinload(ProfilProprietaire.user),
        )
        .where(
            Camion.id == camion_id,
            Camion.proprietaire_id == profil.id,
        )
    )
    camion = result.scalar_one_or_none()
    if not camion:
        raise HTTPException(status_code=404, detail="Camion non trouvé")
    if camion.etat not in ETATS_PUBLIABLES:
        raise HTTPException(status_code=400, detail="Impossible de prolonger : le camion n'est pas en bon état")

    expires = data.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="La nouvelle date d'expiration doit être dans le futur")

    camion.expires_at = expires
    camion.is_public = True
    await db.flush()
    await db.refresh(camion)

    result = await db.execute(
        select(Camion)
        .options(
            selectinload(Camion.photos),
            selectinload(Camion.proprietaire).selectinload(ProfilProprietaire.user),
        )
        .where(Camion.id == camion.id)
    )
    return result.scalar_one()


# ─── Offres ─────────────────────────────────────────

@router.get("/me/offres", response_model=list[OffreOut])
async def list_my_offres(
    current_user: User = Depends(require_verified),
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
            is_editable=_is_editable(o.created_at),
        ))
    return out


@router.post("/me/offres", response_model=OffreOut, status_code=201)
async def create_offre(
    data: OffreCreate,
    current_user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_my_profil(current_user, db)
    from datetime import date as date_type
    now_utc = datetime.now(timezone.utc)
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
        expires_at=now_utc + timedelta(days=OFFRE_EXPIRATION_DAYS),
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
    current_user: User = Depends(require_verified),
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
    current_user: User = Depends(require_verified),
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

    if offre.created_at:
        now = datetime.now(timezone.utc)
        created = offre.created_at.replace(tzinfo=timezone.utc) if offre.created_at.tzinfo is None else offre.created_at
        if now - created > timedelta(minutes=EDIT_WINDOW_MINUTES):
            raise HTTPException(
                status_code=403,
                detail=f"Le délai de modification de {EDIT_WINDOW_MINUTES} minutes est dépassé",
            )

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
    current_user: User = Depends(require_verified),
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


# ─── Camions publics ────────────────────────────────

@router.get("/camions/public", response_model=list[CamionOut])
async def list_public_camions(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    type_camion: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    query = select(Camion).options(
        selectinload(Camion.photos),
        selectinload(Camion.proprietaire).selectinload(ProfilProprietaire.user),
    ).where(
        Camion.is_public == True,
        Camion.etat.in_(ETATS_PUBLIABLES),
        Camion.expires_at > now,
    )
    if type_camion:
        query = query.where(Camion.type_camion == type_camion)
    query = query.order_by(Camion.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    camions = result.scalars().unique().all()
    return camions


@router.get("/camions/public/{camion_id}", response_model=CamionOut)
async def get_public_camion(
    camion_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Camion).options(
            selectinload(Camion.photos),
            selectinload(Camion.proprietaire).selectinload(ProfilProprietaire.user),
        ).where(
            Camion.id == camion_id,
            Camion.is_public == True,
            Camion.etat.in_(ETATS_PUBLIABLES),
            Camion.expires_at > now,
        )
    )
    camion = result.scalar_one_or_none()
    if not camion:
        raise HTTPException(status_code=404, detail="Camion non trouvé ou non public")
    return camion


# ─── Assistance mécanique (propriétaire) ──────────────

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


@router.post("/me/assistance", response_model=AssistanceOut, status_code=201)
async def create_assistance(
    data: AssistanceCreate,
    current_user: User = Depends(require_verified),
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

    from app.utils.notifications import notify_all_admins, notify_user
    from app.models.mecanicien import ProfilMecanicien
    from app.models.enums import UserRole

    mecaniciens_result = await db.execute(
        select(User).where(User.role == UserRole.mecanicien, User.is_active == True)
    )
    mecaniciens = mecaniciens_result.scalars().all()
    for mec in mecaniciens:
        await notify_user(
            db,
            user_id=mec.id,
            titre="Nouvelle demande d'assistance",
            contenu=f"Une demande de type « {data.type_panne} » de urgence « {data.urgence } » a été créée par {current_user.nom_complet}.",
            type_notif="assistance",
            lien="/dashboard/mecanicien/assistance",
        )

    await notify_user(
        db,
        user_id=current_user.id,
        titre="Demande d'assistance envoyée",
        contenu=f"Votre demande d'assistance de type « {data.type_panne } » a été envoyée aux mécaniciens disponibles.",
        type_notif="assistance",
        lien="/dashboard/proprietaire/assistance",
    )

    return _assistance_out(assistance)


@router.get("/me/assistance", response_model=list[AssistanceOut])
async def list_my_assistance(
    current_user: User = Depends(require_verified),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DemandeAssistance)
        .where(DemandeAssistance.demandeur_id == current_user.id)
        .order_by(DemandeAssistance.created_at.desc())
    )
    return [_assistance_out(a) for a in result.scalars().all()]


# ─── Documents ─────────────────────────────────────

UPLOAD_DIR_DOCS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads", "documents")
ALLOWED_DOC_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
MAX_DOC_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post("/me/documents", status_code=201)
async def upload_document(
    type_document: str = Form(...),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role.value != "proprietaire":
        raise HTTPException(status_code=403, detail="Réservé aux propriétaires")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_DOC_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Format non supporté. Veuillez importer une image JPG/PNG ou un fichier PDF.")

    content = await file.read()
    if len(content) > MAX_DOC_SIZE:
        raise HTTPException(status_code=400, detail="Le fichier est trop lourd. La taille maximale autorisée est de 10 Mo.")

    os.makedirs(UPLOAD_DIR_DOCS, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR_DOCS, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    type_doc_enum = None
    for td in TypeDocument:
        if td.value == type_document:
            type_doc_enum = td
            break
    if not type_doc_enum:
        raise HTTPException(status_code=400, detail="Type de document invalide")

    doc = Document(
        id=uuid.uuid4(),
        utilisateur_id=current_user.id,
        type_document=type_doc_enum,
        fichier_url=f"/uploads/documents/{filename}",
        statut="en_attente",
    )
    db.add(doc)
    await db.flush()

    # Dès que la totalité des documents requis est soumise, le compte passe
    # automatiquement en "pending_approval" (en attente de validation admin).
    from app.utils.verification import sync_verification_after_upload
    await sync_verification_after_upload(db, current_user)

    await db.refresh(doc)
    return {
        "id": str(doc.id),
        "type_document": type_document,
        "fichier_url": doc.fichier_url,
        "statut": "en_attente",
        "message": "Document uploadé avec succès",
    }


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
