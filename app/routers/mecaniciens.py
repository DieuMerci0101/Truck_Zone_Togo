import math
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

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

# Alias compatible anglais (API partenaires)
alias_router = APIRouter(prefix="/api/mechanics", tags=["Mechanics (alias)"])

PROOF_UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "uploads",
    "justificatifs",
)
PROOF_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}
PROOF_MAX_FILE_SIZE = 10 * 1024 * 1024
VERIFICATION_STATUS = {"pending_upload", "pending_approval", "approved", "rejected"}


def _localisation_wkt(lat: float, lng: float) -> str:
    return f"POINT({lng} {lat})"


def _parse_wkt(loc: str | None) -> tuple[float, float]:
    if not loc:
        return 0.0, 0.0
    try:
        coords = loc.replace("POINT(", "").replace(")", "").split()
        lng, lat = float(coords[0]), float(coords[1])
        return lat, lng
    except (ValueError, IndexError):
        return 0.0, 0.0


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


class MecanicienPositionUpdate(BaseModel):
    localisation_lat: float = Field(..., ge=-90, le=90)
    localisation_lng: float = Field(..., ge=-180, le=180)


def _assistance_out(a: DemandeAssistance) -> AssistanceOut:
    return AssistanceOut.model_validate(a)


async def _get_or_create_profil(
    current_user: User,
    db: AsyncSession,
) -> ProfilMecanicien:
    """
    Retourne le profil mécanicien de l'utilisateur, et le crée s'il n'existe pas
    (comptes créés avant la création automatique du profil à l'inscription).
    Évite l'erreur "Profil mécanicien non trouvé" qui bloquait l'upload du justificatif.
    """
    result = await db.execute(
        select(ProfilMecanicien).where(ProfilMecanicien.user_id == current_user.id)
    )
    profil = result.scalar_one_or_none()
    if profil:
        return profil

    from app.models.enums import TarificationMecanicien

    profil = ProfilMecanicien(
        id=uuid.uuid4(),
        user_id=current_user.id,
        specialites=[],
        annees_experience=0,
        certifications=[],
        tarification=TarificationMecanicien.payant,
        rayon_intervention=30,
        bio=None,
        photo_url=None,
    )
    db.add(profil)
    await db.flush()
    await db.refresh(profil)
    profil.user = current_user
    return profil


@router.get("/me", response_model=ProfilMecanicienOut)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profil = await _get_or_create_profil(current_user, db)
    if profil.user is None:
        profil.user = current_user
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


@router.put("/me/position")
async def update_my_position(
    data: MecanicienPositionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProfilMecanicien).where(ProfilMecanicien.user_id == current_user.id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil mécanicien non trouvé")

    profil.localisation = _localisation_wkt(data.localisation_lat, data.localisation_lng)
    await db.flush()
    return {"message": "Position mise à jour", "localisation_lat": data.localisation_lat, "localisation_lng": data.localisation_lng}


# ─── Vérification du mécanicien (justificatif) ──────

@router.post("/upload-proof", status_code=201)
@alias_router.post("/upload-proof", status_code=201)
async def upload_proof(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload du justificatif du mécanicien (attestation / diplôme / certificat).
    Passe le statut de vérification à 'pending_approval'.
    """
    if current_user.role.value != "mecanicien":
        raise HTTPException(status_code=403, detail="Réservé aux mécaniciens")

    profil = await _get_or_create_profil(current_user, db)
    if profil.verification_status == "approved":
        raise HTTPException(status_code=400, detail="Votre compte est déjà validé")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in PROOF_ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Format non supporté. Veuillez importer une image JPG/PNG ou un fichier PDF.")

    content = await file.read()
    if len(content) > PROOF_MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="Le fichier est trop lourd. La taille maximale autorisée est de 10 Mo.")

    os.makedirs(PROOF_UPLOAD_DIR, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(PROOF_UPLOAD_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)

    profil.proof_document_url = f"/uploads/justificatifs/{filename}"
    profil.verification_status = "pending_approval"
    # Synchronise aussi le statut global du compte
    from app.utils.verification import set_verification_status, PENDING_APPROVAL
    set_verification_status(current_user, PENDING_APPROVAL)
    await db.flush()

    # Informe les administrateurs qu'un justificatif attend leur examen
    from app.utils.notifications import notify_all_admins
    await notify_all_admins(
        db,
        titre="Nouveau justificatif à vérifier",
        contenu=f"{current_user.nom_complet} a soumis son justificatif mécanicien. Il attend votre validation.",
        type_notif="document",
        lien="/dashboard/admin/documents",
    )

    return {
        "message": "Votre document a été soumis avec succès. Votre compte est actuellement en attente de confirmation par l'administrateur.",
        "proof_document_url": profil.proof_document_url,
        "verification_status": profil.verification_status,
    }


@router.get("/verification")
async def get_my_verification(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Statut de vérification du mécanicien connecté."""
    if current_user.role.value != "mecanicien":
        raise HTTPException(status_code=403, detail="Réservé aux mécaniciens")
    profil = await _get_or_create_profil(current_user, db)
    return {
        "verification_status": profil.verification_status,
        "proof_document_url": profil.proof_document_url,
        "is_verified": current_user.is_verified,
    }


# ─── Assistance ─────────────────────────────────────

@router.get("/assistance/mes-demandes", response_model=list[AssistanceOut])
async def list_my_assistance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DemandeAssistance)
        .options(
            selectinload(DemandeAssistance.demandeur),
            selectinload(DemandeAssistance.mecanicien).selectinload(ProfilMecanicien.user),
        )
        .where(DemandeAssistance.demandeur_id == current_user.id)
        .order_by(DemandeAssistance.created_at.desc())
    )
    return [_assistance_out(a) for a in result.scalars().all()]


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
    assistance.demandeur = current_user

    from app.utils.notifications import notify_all_admins, notify_user
    await notify_all_admins(
        db,
        titre="Nouvelle demande d'assistance",
        contenu=f"{current_user.nom_complet} demande une assistance de type « {data.type_panne} » (urgence « {data.urgence} »).",
        type_notif="assistance",
        lien="/dashboard/admin/assistance",
    )
    await notify_user(
        db,
        user_id=current_user.id,
        titre="Demande d'assistance envoyée",
        contenu=f"Votre demande d'assistance de type « {data.type_panne} » a été transmise aux administrateurs et mécaniciens disponibles.",
        type_notif="assistance",
        lien="/dashboard/chauffeur/assistance",
    )

    return _assistance_out(assistance)


@router.get("/assistance/disponibles", response_model=list[AssistanceOut])
async def list_available_assistance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Liste toutes les demandes actives (non terminées) pour les mécaniciens."""
    result = await db.execute(
        select(DemandeAssistance)
        .options(
            selectinload(DemandeAssistance.demandeur),
            selectinload(DemandeAssistance.mecanicien).selectinload(ProfilMecanicien.user),
        )
        .where(DemandeAssistance.statut != "terminee")
        .order_by(DemandeAssistance.created_at.desc())
    )
    return [_assistance_out(a) for a in result.scalars().all()]


@router.put("/assistance/{assistance_id}/prendre")
async def take_assistance(
    assistance_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Le mécanicien prend en charge une demande."""
    result = await db.execute(
        select(DemandeAssistance).where(DemandeAssistance.id == assistance_id)
    )
    assistance = result.scalar_one_or_none()
    if not assistance:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    if assistance.statut != "en_attente":
        raise HTTPException(status_code=400, detail="Demande déjà prise en charge")

    # Récupérer le profil mécanicien
    profil_result = await db.execute(
        select(ProfilMecanicien).where(ProfilMecanicien.user_id == current_user.id)
    )
    profil = profil_result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=400, detail="Profil mécanicien introuvable")

    assistance.mecanicien_id = profil.id
    assistance.statut = "pris_en_charge"
    await db.flush()
    return {"message": "Demande prise en charge", "statut": "pris_en_charge"}


@router.get("/assistance/{assistance_id}", response_model=AssistanceOut)
async def get_assistance(
    assistance_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DemandeAssistance)
        .options(
            selectinload(DemandeAssistance.demandeur),
            selectinload(DemandeAssistance.mecanicien).selectinload(ProfilMecanicien.user),
        )
        .where(DemandeAssistance.id == assistance_id)
    )
    assistance = result.scalar_one_or_none()
    if not assistance:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    return _assistance_out(assistance)


@router.put("/assistance/{assistance_id}/statut")
async def update_assistance_statut(
    assistance_id: uuid.UUID,
    data: AssistanceUpdateStatut,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DemandeAssistance)
        .options(
            selectinload(DemandeAssistance.demandeur),
            selectinload(DemandeAssistance.mecanicien).selectinload(ProfilMecanicien.user),
        )
        .where(DemandeAssistance.id == assistance_id)
    )
    assistance = result.scalar_one_or_none()
    if not assistance:
        raise HTTPException(status_code=404, detail="Demande non trouvée")

    # Seul le mécanicien assigné peut modifier le statut
    if assistance.mecanicien_id:
        profil_result = await db.execute(
            select(ProfilMecanicien).where(ProfilMecanicien.user_id == current_user.id)
        )
        profil = profil_result.scalar_one_or_none()
        if not profil or str(profil.id) != str(assistance.mecanicien_id):
            raise HTTPException(status_code=403, detail="Seul le mécanicien assigné peut modifier le statut")

    assistance.statut = data.statut
    await db.flush()
    return {"message": "Statut mis à jour", "statut": assistance.statut}


# ─── Nearby & single mecanicien ────────────────────
# IMPORTANT: these parametrized routes MUST be last to avoid catching
# /assistance/* or /me paths.

@router.get("/proches", response_model=list[ProfilMecanicienOut])
async def get_mecaniciens_proches(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    rayon_km: int = Query(50, gt=0),
    specialite: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(ProfilMecanicien)
        .options(selectinload(ProfilMecanicien.user))
        .where(ProfilMecanicien.disponibilite == "disponible")
    )
    if specialite:
        query = query.where(ProfilMecanicien.specialites.any(specialite))
    result = await db.execute(query.limit(200))
    all_profiles = result.scalars().all()

    nearby = []
    for p in all_profiles:
        p_lat, p_lng = _parse_wkt(p.localisation)
        if p_lat == 0.0 and p_lng == 0.0:
            continue
        dist = _haversine(lat, lng, p_lat, p_lng)
        if dist <= rayon_km:
            nearby.append((dist, p))

    nearby.sort(key=lambda x: x[0])
    return [p for _, p in nearby[:50]]


@router.get("/", response_model=list[ProfilMecanicienOut])
async def list_mecaniciens(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    specialite: str | None = None,
    disponibilite: str | None = None,
    tarification: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(ProfilMecanicien).options(selectinload(ProfilMecanicien.user))
    if specialite:
        query = query.where(ProfilMecanicien.specialites.any(specialite))
    if disponibilite:
        query = query.where(ProfilMecanicien.disponibilite == disponibilite)
    if tarification:
        query = query.where(ProfilMecanicien.tarification == tarification)
    result = await db.execute(query.offset(skip).limit(limit))
    return result.scalars().all()


@router.get("/{mecanicien_id}", response_model=ProfilMecanicienOut)
async def get_mecanicien(
    mecanicien_id: uuid.UUID, db: AsyncSession = Depends(get_db)
):
    result = await db.execute(
        select(ProfilMecanicien)
        .options(selectinload(ProfilMecanicien.user))
        .where(ProfilMecanicien.id == mecanicien_id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Mécanicien non trouvé")
    return profil
