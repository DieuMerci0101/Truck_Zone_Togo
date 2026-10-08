import math
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.models.mecanicien import ProfilMecanicien
from app.models.assistance import DemandeAssistance
from app.models.proposition import PropositionAssistance
from app.models.enums import DisponibiliteMecanicien, StatutAssistance, StatutProposition, UserRole
from app.routers.auth import get_current_user
from app.services.storage import save_upload
from app.schemas.mecanicien import (
    AssistanceCreate,
    AssistanceOut,
    AssistanceUpdateStatut,
    MecanicienPositionOut,
    ProfilMecanicienOut,
    ProfilMecanicienUpdate,
    PropositionMecanicienOut,
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


async def _mecaniciens_proches(
    db: AsyncSession,
    lat: float,
    lng: float,
    max_rayon_km: float | None = None,
) -> list[tuple[ProfilMecanicien, float]]:
    """
    Retourne les mécaniciens à proximité ÉLIGIBLES pour une nouvelle demande :
    position temps réel activée, compte vérifié, NON indisponible, et situés
    dans la limite de leur rayon d'intervention (plafonné par
    `MECHANIC_ASSISTANCE_RADIUS_KM`). Triés par distance croissante.
    """
    if max_rayon_km is None:
        max_rayon_km = get_settings().mechanic_assistance_radius_km
    result = await db.execute(
        select(ProfilMecanicien)
        .options(selectinload(ProfilMecanicien.user))
        .where(
            ProfilMecanicien.position_active == True,  # noqa: E712
            ProfilMecanicien.verification_status == "approved",
            ProfilMecanicien.disponibilite != DisponibiliteMecanicien.indisponible,
        )
    )
    proches: list[tuple[ProfilMecanicien, float]] = []
    for p in result.scalars().all():
        p_lat, p_lng = _parse_wkt(p.localisation)
        if p_lat == 0.0 and p_lng == 0.0:
            continue
        dist = _haversine(lat, lng, p_lat, p_lng)
        if dist <= min(p.rayon_intervention or 30, max_rayon_km):
            proches.append((p, round(dist, 1)))
    proches.sort(key=lambda x: x[1])
    return proches


class MecanicienPositionUpdate(BaseModel):
    localisation_lat: float = Field(..., ge=-90, le=90)
    localisation_lng: float = Field(..., ge=-180, le=180)


class MecanicienActivationRequest(BaseModel):
    localisation_lat: float | None = Field(None, ge=-90, le=90)
    localisation_lng: float | None = Field(None, ge=-180, le=180)


def _assistance_out(
    a: DemandeAssistance,
    distance_km: float | None = None,
    profil_mecanicien: ProfilMecanicien | None = None,
) -> AssistanceOut:
    """
    Sérialise une demande d'assistance, y compris l'historique des propositions
    de prise en charge. Si `profil_mecanicien` est fourni (mécanicien connecté),
    `ma_proposition` pointe vers SA proposition.
    """
    out = AssistanceOut.model_validate(a)
    if distance_km is not None:
        out.distance_km = distance_km

    out.propositions = []
    try:
        out.propositions = [
            PropositionMecanicienOut.model_validate(p)
            for p in (list(a.propositions) if a.propositions is not None else [])
        ]
    except Exception:  # noqa: BLE001 — objet fraîchement créé, non chargé
        out.propositions = []
    out.nb_propositions_en_attente = sum(
        1 for p in out.propositions if p.statut == StatutProposition.en_attente.value
    )
    if profil_mecanicien is not None:
        for p in out.propositions:
            if str(p.mecanicien_id) == str(profil_mecanicien.id):
                out.ma_proposition = p
                break
    return out


async def notifier_mecaniciens_proches(
    db: AsyncSession,
    assistance: DemandeAssistance,
    demandeur: User,
) -> int:
    """
    Notifie TOUS les mécaniciens éligibles (proches + disponibles + vérifiés)
    d'une nouvelle demande d'assistance : notification en base + Web Push,
    puis rafraîchissement temps réel de la file d'attente (WebSocket).
    Retourne le nombre de mécaniciens notifiés.
    """
    from app.assistance_events import broadcast_assistance_event
    from app.utils.notifications import notify_user

    lat, lng = _parse_wkt(assistance.localisation)
    if (lat, lng) == (0.0, 0.0):
        return 0

    proches = await _mecaniciens_proches(db, lat, lng)
    type_panne = (
        assistance.type_panne.value
        if hasattr(assistance.type_panne, "value")
        else str(assistance.type_panne)
    )
    urgence = (
        assistance.urgence.value
        if hasattr(assistance.urgence, "value")
        else str(assistance.urgence)
    )
    for mecanicien, dist in proches:
        await notify_user(
            db,
            user_id=mecanicien.user_id,
            titre="🔧 Nouvelle demande d'assistance mécanique",
            contenu=(
                "Nouvelle demande d'assistance mécanique disponible à proximité. "
                f"{demandeur.nom_complet} demande « {type_panne} » (urgence « {urgence} ») "
                f"à {dist:.0f} km de vous. Consultez la demande pour proposer votre intervention."
            ),
            type_notif="assistance",
            lien="/dashboard/mecanicien/assistance",
            metadata={
                "demande_id": str(assistance.id),
                "distance_km": dist,
            },
            push=True,
        )
    await broadcast_assistance_event(
        {
            "type": "assistance_new",
            "demande_id": str(assistance.id),
            "demandeur_id": str(assistance.demandeur_id),
        }
    )
    return len(proches)


async def _profil_mecanicien_of(
    db: AsyncSession, user_id: uuid.UUID
) -> ProfilMecanicien | None:
    result = await db.execute(
        select(ProfilMecanicien).where(ProfilMecanicien.user_id == user_id)
    )
    return result.scalar_one_or_none()


def _is_demandeur(current_user: User, assistance: DemandeAssistance) -> bool:
    """Seul le demandeur (chauffeur/propriétaire) peut choisir le mécanicien."""
    if current_user.role in (UserRole.mecanicien, UserRole.admin):
        return False
    return str(assistance.demandeur_id) == str(current_user.id)


def _load_propositions_options():
    return (
        selectinload(DemandeAssistance.propositions).selectinload(
            PropositionAssistance.mecanicien
        ).selectinload(ProfilMecanicien.user),
        selectinload(DemandeAssistance.demandeur),
        selectinload(DemandeAssistance.mecanicien).selectinload(ProfilMecanicien.user),
    )


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
    """
    Met à jour la position du mécanicien connecté et l'active (position temps réel).
    """
    result = await db.execute(
        select(ProfilMecanicien).where(ProfilMecanicien.user_id == current_user.id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil mécanicien non trouvé")

    profil.localisation = _localisation_wkt(data.localisation_lat, data.localisation_lng)
    profil.position_active = True
    profil.position_updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {
        "message": "Position mise à jour",
        "localisation_lat": data.localisation_lat,
        "localisation_lng": data.localisation_lng,
        "position_active": True,
    }


async def _get_mecanicien_profil_or_404(current_user: User, db: AsyncSession) -> ProfilMecanicien:
    result = await db.execute(
        select(ProfilMecanicien).where(ProfilMecanicien.user_id == current_user.id)
    )
    profil = result.scalar_one_or_none()
    if not profil:
        raise HTTPException(status_code=404, detail="Profil mécanicien non trouvé")
    return profil


@router.put("/localisation/activer")
@alias_router.post("/location/activate")
async def activer_position(
    data: MecanicienActivationRequest | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Active la position temps réel du mécanicien (optionnellement avec des coordonnées).
    """
    profil = await _get_mecanicien_profil_or_404(current_user, db)

    if data and data.localisation_lat is not None and data.localisation_lng is not None:
        profil.localisation = _localisation_wkt(data.localisation_lat, data.localisation_lng)

    p_lat, p_lng = _parse_wkt(profil.localisation)
    if p_lat == 0.0 and p_lng == 0.0:
        raise HTTPException(
            status_code=400,
            detail="Aucune position enregistrée. Fournissez une position ou localisez-vous d'abord.",
        )

    profil.position_active = True
    profil.position_updated_at = datetime.now(timezone.utc)
    await db.flush()
    return {"message": "Position activée — vous êtes visible par les chauffeurs à proximité", "position_active": True}


@router.put("/localisation/desactiver")
@alias_router.post("/location/deactivate")
async def desactiver_position(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Désactive la position temps réel du mécanicien."""
    profil = await _get_mecanicien_profil_or_404(current_user, db)
    profil.position_active = False
    await db.flush()
    return {"message": "Position désactivée", "position_active": False}


@router.get("/actifs", response_model=list[MecanicienPositionOut])
async def get_mecaniciens_actifs(
    lat: float | None = Query(None, ge=-90, le=90),
    lng: float | None = Query(None, ge=-180, le=180),
    rayon_km: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste tous les mécaniciens ayant activé leur position temps réel.
    Si lat/lng sont fournis, trie par distance croissante (optionnellement filtrés par rayon).
    """
    result = await db.execute(
        select(ProfilMecanicien)
        .options(selectinload(ProfilMecanicien.user))
        .where(ProfilMecanicien.position_active == True)
    )
    profiles = result.scalars().all()

    items: list[MecanicienPositionOut] = []
    for p in profiles:
        p_lat, p_lng = _parse_wkt(p.localisation)
        if p_lat == 0.0 and p_lng == 0.0:
            continue
        dist = None
        if lat is not None and lng is not None:
            dist = round(_haversine(lat, lng, p_lat, p_lng), 1)
            if rayon_km and dist > rayon_km:
                continue
        user = p.user
        items.append(
            MecanicienPositionOut(
                id=p.id,
                nom_complet=user.nom_complet if user else "",
                telephone=user.telephone if user else None,
                photo_url=user.photo_profil if user else None,
                specialites=p.specialites or [],
                disponibilite=p.disponibilite.value if hasattr(p.disponibilite, "value") else p.disponibilite,
                localisation_lat=p_lat,
                localisation_lng=p_lng,
                position_active=bool(p.position_active),
                position_updated_at=p.position_updated_at,
                distance_km=dist,
            )
        )

    if lat is not None and lng is not None:
        items.sort(key=lambda x: (x.distance_km is None, x.distance_km if x.distance_km is not None else 0))
    return items


@alias_router.patch("/location")
async def update_location_alias(
    data: MecanicienPositionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Alias API partenaires : PATCH /api/mechanics/location."""
    return await update_my_position(data, current_user, db)


@alias_router.get("/locations", response_model=list[MecanicienPositionOut])
async def list_mechanics_locations_alias(
    lat: float | None = Query(None, ge=-90, le=90),
    lng: float | None = Query(None, ge=-180, le=180),
    rayon_km: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Alias API partenaires : GET /api/mechanics/locations."""
    return await get_mecaniciens_actifs(lat=lat, lng=lng, rayon_km=rayon_km, current_user=current_user, db=db)


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

    profil.proof_document_url = save_upload(content, "justificatifs", ext)
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
        lien="/admin/dashboard/documents",
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
        .options(*_load_propositions_options())
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
    from app.assistance_events import broadcast_assistance_event
    await notify_all_admins(
        db,
        titre="Nouvelle demande d'assistance",
        contenu=f"{current_user.nom_complet} demande une assistance de type « {data.type_panne} » (urgence « {data.urgence} »).",
        type_notif="assistance",
        lien="/admin/dashboard/assistance",
    )

    # ── Module 3 : notifier les mécaniciens à proximité (position active,
    #    vérifiés, disponibles, dans leur rayon d'intervention) + push.
    await notifier_mecaniciens_proches(db, assistance, current_user)

    urgence_valeur = data.urgence.value if hasattr(data.urgence, "value") else str(data.urgence)
    est_urgent = urgence_valeur.lower() in ("haute", "critique")
    await notify_user(
        db,
        user_id=current_user.id,
        titre="Demande d'assistance envoyée",
        contenu=f"Votre demande d'assistance de type « {data.type_panne} » a été transmise aux administrateurs et mécaniciens disponibles.",
        type_notif="assistance",
        lien="/dashboard/chauffeur/assistance",
        metadata={"demande_id": str(assistance.id), "urgence": urgence_valeur},
        push=True,
        sms=True,
        urgent=est_urgent,
    )

    return _assistance_out(assistance)


@router.get("/assistance/disponibles", response_model=list[AssistanceOut])
async def list_available_assistance(
    lat: float | None = Query(None, ge=-90, le=90),
    lng: float | None = Query(None, ge=-180, le=180),
    rayon_km: float | None = Query(None, gt=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste les demandes actives (non terminées) pour les mécaniciens.
    Si `lat`/`lng` sont fournis, chaque demande est enrichie de sa distance
    (`distance_km`) et filtrée par `rayon_km` (si fourni) — la file d'attente
    « premier arrivé » se limite ainsi aux interventions géographiquement
    pertinentes pour le mécanicien.
    """
    result = await db.execute(
        select(DemandeAssistance)
        .options(*_load_propositions_options())
        .where(DemandeAssistance.statut != "terminee")
        .order_by(DemandeAssistance.created_at.desc())
    )
    demandes = result.scalars().all()

    profil = await _profil_mecanicien_of(db, current_user.id)
    items: list[AssistanceOut] = []
    for d in demandes:
        dist = None
        if lat is not None and lng is not None:
            d_lat, d_lng = _parse_wkt(d.localisation)
            if d_lat != 0.0 and d_lng != 0.0:
                dist = round(_haversine(lat, lng, d_lat, d_lng), 1)
                if rayon_km and dist > rayon_km:
                    continue
        items.append(_assistance_out(d, distance_km=dist, profil_mecanicien=profil))

    if lat is not None and lng is not None:
        items.sort(key=lambda x: (x.distance_km is None, x.distance_km or 0))
    return items


def _lien_demande(assistance: DemandeAssistance) -> str:
    """Lien de la demande selon le rôle du demandeur (chauffeur / propriétaire)."""
    role = assistance.demandeur.role.value if assistance.demandeur else "chauffeur"
    if role == "proprietaire":
        return "/dashboard/proprietaire/assistance"
    return "/dashboard/chauffeur/assistance"


def _distance_demande_mecanicien(
    assistance: DemandeAssistance, profil: ProfilMecanicien
) -> float | None:
    d_lat, d_lng = _parse_wkt(assistance.localisation)
    p_lat, p_lng = _parse_wkt(profil.localisation)
    if (d_lat, d_lng) == (0.0, 0.0) or (p_lat, p_lng) == (0.0, 0.0):
        return None
    return round(_haversine(d_lat, d_lng, p_lat, p_lng), 1)


@router.put("/assistance/{assistance_id}/prendre")
async def propose_assistance(
    assistance_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Le mécanicien PROPOSE son assistance — il n'est PAS sélectionné.

    Il est simplement ajouté à la liste des mécaniciens intéressés, avec le
    statut « en attente de validation du chauffeur ». Plusieurs mécaniciens
    peuvent proposer la même demande ; seul le chauffeur (demandeur) choisit
    ensuite celui qui interviendra.

    La ligne de la demande est verrouillée (`FOR UPDATE`) pendant la lecture
    du statut : une proposition ne peut pas être créée sur une demande qui
    vient d'être attribuée (course possible avec la sélection du chauffeur).
    """
    if current_user.role != UserRole.mecanicien:
        raise HTTPException(
            status_code=403, detail="Seul un mécanicien peut proposer son assistance"
        )

    profil = await _get_or_create_profil(current_user, db)

    locked = await db.execute(
        select(DemandeAssistance)
        .options(*_load_propositions_options())
        .where(DemandeAssistance.id == assistance_id)
        .with_for_update()
    )
    assistance = locked.scalar_one_or_none()
    if not assistance:
        raise HTTPException(status_code=404, detail="Demande non trouvée")

    if assistance.statut != StatutAssistance.en_attente:
        raise HTTPException(
            status_code=400,
            detail="Cette demande est déjà attribuée à un autre mécanicien",
        )

    # Idempotence : une seule proposition par mécanicien et par demande.
    existing_result = await db.execute(
        select(PropositionAssistance).where(
            PropositionAssistance.assistance_id == assistance_id,
            PropositionAssistance.mecanicien_id == profil.id,
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        return {
            "message": "Votre proposition est déjà enregistrée",
            "statut": existing.statut.value,
            "proposition": PropositionMecanicienOut.model_validate(existing),
        }

    proposition = PropositionAssistance(
        id=uuid.uuid4(),
        assistance_id=assistance.id,
        mecanicien_id=profil.id,
        distance_km=_distance_demande_mecanicien(assistance, profil),
        statut=StatutProposition.en_attente,
    )
    db.add(proposition)
    try:
        await db.flush()
    except IntegrityError:
        # Concurrence (double clic / requêtes simultanées) : retour idempotent.
        await db.rollback()
        again = await db.execute(
            select(PropositionAssistance).where(
                PropositionAssistance.assistance_id == assistance_id,
                PropositionAssistance.mecanicien_id == profil.id,
            )
        )
        row = again.scalar_one_or_none()
        if row:
            return {
                "message": "Votre proposition est déjà enregistrée",
                "statut": row.statut.value,
                "proposition": PropositionMecanicienOut.model_validate(row),
            }
        raise HTTPException(
            status_code=409, detail="Impossible d'enregistrer votre proposition"
        )
    await db.refresh(proposition)

    from app.assistance_events import broadcast_assistance_event
    from app.utils.notifications import notify_user

    # Le demandeur est informé qu'un mécanicien a proposé (Notification 2).
    await notify_user(
        db,
        user_id=assistance.demandeur_id,
        titre="Un mécanicien propose son assistance",
        contenu=(
            f"{current_user.nom_complet} propose son assistance pour votre demande "
            f"d'assistance (« {assistance.type_panne} »). "
            "Consultez la demande pour choisir le mécanicien qui interviendra."
        ),
        type_notif="assistance",
        lien=_lien_demande(assistance),
        metadata={
            "demande_id": str(assistance.id),
            "mecanicien_id": str(profil.id),
            "proposition_id": str(proposition.id),
        },
        email=True,
        push=True,
    )
    await broadcast_assistance_event(
        {
            "type": "assistance_proposal",
            "demande_id": str(assistance.id),
            "demandeur_id": str(assistance.demandeur_id),
        }
    )

    return {
        "message": "Proposition enregistrée — en attente de validation du chauffeur",
        "statut": proposition.statut.value,
        "proposition": PropositionMecanicienOut.model_validate(proposition),
    }


@router.get(
    "/assistance/{assistance_id}/propositions",
    response_model=list[PropositionMecanicienOut],
)
async def list_propositions(
    assistance_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste des mécaniciens ayant proposé leur assistance.
    - le demandeur (chauffeur/propriétaire) voit TOUS les mécaniciens intéressés ;
    - un mécanicien ne voit que SA propre proposition ;
    - les autres rôles sont refusés (403).
    """
    result = await db.execute(
        select(DemandeAssistance)
        .options(*_load_propositions_options())
        .where(DemandeAssistance.id == assistance_id)
    )
    assistance = result.scalar_one_or_none()
    if not assistance:
        raise HTTPException(status_code=404, detail="Demande non trouvée")

    if _is_demandeur(current_user, assistance):
        propositions = list(assistance.propositions)
    elif current_user.role == UserRole.mecanicien:
        profil = await _profil_mecanicien_of(db, current_user.id)
        if not profil:
            raise HTTPException(status_code=400, detail="Profil mécanicien introuvable")
        propositions = [
            p
            for p in assistance.propositions
            if str(p.mecanicien_id) == str(profil.id)
        ]
    else:
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    # Les propositions en attente d'abord, puis par distance croissante.
    propositions.sort(
        key=lambda p: (
            p.statut != StatutProposition.en_attente,
            p.distance_km if p.distance_km is not None else 99999,
        )
    )
    return [PropositionMecanicienOut.model_validate(p) for p in propositions]


async def _get_assistance_for_update(
    db: AsyncSession, assistance_id: uuid.UUID
) -> DemandeAssistance:
    result = await db.execute(
        select(DemandeAssistance)
        .options(*_load_propositions_options())
        .where(DemandeAssistance.id == assistance_id)
        .with_for_update()
    )
    assistance = result.scalar_one_or_none()
    if not assistance:
        raise HTTPException(status_code=404, detail="Demande non trouvée")
    return assistance


@router.put("/assistance/{assistance_id}/propositions/{mecanicien_id}/accept")
async def accept_proposition(
    assistance_id: uuid.UUID,
    mecanicien_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Le CHAUFFEUR (demandeur) sélectionne le mécanicien qui interviendra.

    Sélection transactionnelle et exclusive :
    - la ligne de la demande est verrouillée (`FOR UPDATE`) ;
    - le statut doit toujours être `en_attente` (sinon 400) ;
    - la proposition retenue passe à `accepte` ;
    - TOUTES les autres propositions passent à `refuse` automatiquement ;
    - la demande passe au statut existant `assignee` (mécanicien sélectionné).

    Impossible de sélectionner deux mécaniciens pour la même demande.
    """
    assistance = await _get_assistance_for_update(db, assistance_id)

    if not _is_demandeur(current_user, assistance):
        raise HTTPException(
            status_code=403,
            detail="Seul le chauffeur ayant créé la demande peut sélectionner un mécanicien",
        )

    if assistance.statut != StatutAssistance.en_attente:
        raise HTTPException(
            status_code=400,
            detail="Cette demande a déjà été attribuée à un mécanicien",
        )

    cible = next(
        (p for p in assistance.propositions if str(p.id) == str(mecanicien_id)), None
    )
    if cible is None:
        raise HTTPException(
            status_code=404,
            detail="Ce mécanicien n'a pas proposé son assistance pour cette demande",
        )
    if cible.statut != StatutProposition.en_attente:
        raise HTTPException(
            status_code=400,
            detail="Cette proposition n'est plus en attente de validation",
        )

    now = datetime.now(timezone.utc)
    rejetes: list[PropositionAssistance] = []
    for p in assistance.propositions:
        if str(p.id) == str(mecanicien_id):
            p.statut = StatutProposition.accepte
        else:
            if p.statut == StatutProposition.en_attente:
                rejetes.append(p)
            p.statut = StatutProposition.refuse

    profil = cible.mecanicien
    assistance.mecanicien = profil
    assistance.mecanicien_id = profil.id
    assistance.statut = StatutAssistance.assignee
    assistance.pris_en_charge_at = now
    await db.flush()

    from app.assistance_events import broadcast_assistance_event
    from app.models.message import Message
    from app.routers.conversations import get_or_create_direct_conversation
    from app.utils.notifications import notify_user

    # ── Conversation privée + premier message du chauffeur ──
    conv = await get_or_create_direct_conversation(
        db, assistance.demandeur_id, profil.user_id
    )
    nom_mec = profil.user.nom_complet if profil.user else "mécanicien"
    db.add(
        Message(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            expediteur_id=assistance.demandeur_id,
            contenu=(
                f"Bonjour {nom_mec}, je retiens votre profil pour "
                f"mon assistance (« {assistance.type_panne} »). "
                "Pouvons-nous convenir de l'heure de votre intervention ?"
            ),
            type="texte",
        )
    )
    conv.updated_at = now

    # ── Notification 3 : mécanicien ACCEPTÉ ──
    await notify_user(
        db,
        user_id=profil.user_id,
        titre="Votre assistance a été acceptée",
        contenu=(
            "✅ Votre assistance a été acceptée. Le chauffeur vous a sélectionné "
            "pour intervenir sur cette panne."
        ),
        type_notif="assistance",
        lien=f"/dashboard/chat?conv={conv.id}",
        metadata={
            "demande_id": str(assistance.id),
            "mecanicien_id": str(profil.id),
            "conversation_id": str(conv.id),
            "resultat": "accepte",
        },
        email=True,
        push=True,
    )

    # ── Notification 4 : mécaniciens REJETÉS automatiquement ──
    for p in rejetes:
        await notify_user(
            db,
            user_id=p.mecanicien.user_id,
            titre="Demande déjà prise en charge",
            contenu=(
                "ℹ️ Cette demande d'assistance a déjà été prise en charge par un "
                "autre mécanicien situé à proximité du lieu de la panne. "
                "Merci pour votre disponibilité."
            ),
            type_notif="assistance",
            lien="/dashboard/mecanicien/assistance",
            metadata={
                "demande_id": str(assistance.id),
                "mecanicien_id": str(p.mecanicien_id),
                "resultat": "refuse",
            },
            push=True,
        )

    # ── Confirmation au chauffeur ──
    await notify_user(
        db,
        user_id=assistance.demandeur_id,
        titre="Mécanicien sélectionné",
        contenu=(
            "✅ Le mécanicien sélectionné a été informé de votre choix. "
            f"Vous pouvez échanger avec {nom_mec} dès maintenant."
        ),
        type_notif="assistance",
        lien=f"/dashboard/chat?conv={conv.id}",
        metadata={
            "demande_id": str(assistance.id),
            "mecanicien_id": str(profil.id),
            "conversation_id": str(conv.id),
        },
        push=True,
    )

    await broadcast_assistance_event(
        {
            "type": "assistance_taken",
            "demande_id": str(assistance.id),
            "demandeur_id": str(assistance.demandeur_id),
            "mecanicien_id": str(profil.id),
        }
    )

    return {
        "message": "Mécanicien sélectionné",
        "statut": assistance.statut.value,
        "mecanicien_id": str(profil.id),
        "conversation_id": str(conv.id),
        "propositions_refusees": len(rejetes),
    }


@router.put("/assistance/{assistance_id}/propositions/{mecanicien_id}/reject")
async def reject_proposition(
    assistance_id: uuid.UUID,
    mecanicien_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Le CHAUFFEUR rejette une proposition précise (avant d'en accepter une autre).
    Une fois qu'un mécanicien est sélectionné, plus aucune modification n'est
    possible (400) — la sélection est définitive.
    """
    assistance = await _get_assistance_for_update(db, assistance_id)

    if not _is_demandeur(current_user, assistance):
        raise HTTPException(
            status_code=403,
            detail="Seul le chauffeur ayant créé la demande peut rejeter une proposition",
        )
    if assistance.statut != StatutAssistance.en_attente:
        raise HTTPException(
            status_code=400,
            detail="Cette demande a déjà été attribuée à un mécanicien",
        )

    cible = next(
        (p for p in assistance.propositions if str(p.id) == str(mecanicien_id)), None
    )
    if cible is None:
        raise HTTPException(status_code=404, detail="Proposition non trouvée")
    if cible.statut != StatutProposition.en_attente:
        raise HTTPException(
            status_code=400, detail="Cette proposition n'est plus en attente"
        )

    cible.statut = StatutProposition.refuse
    await db.flush()

    from app.utils.notifications import notify_user

    await notify_user(
        db,
        user_id=cible.mecanicien.user_id,
        titre="Proposition non retenue",
        contenu=(
            "ℹ️ Le chauffeur n'a pas retenu votre proposition pour cette demande "
            "d'assistance. Merci pour votre disponibilité."
        ),
        type_notif="assistance",
        lien="/dashboard/mecanicien/assistance",
        metadata={
            "demande_id": str(assistance.id),
            "mecanicien_id": str(cible.mecanicien_id),
            "resultat": "refuse",
        },
        push=True,
    )

    return {
        "message": "Proposition rejetée",
        "statut": cible.statut.value,
        "nb_propositions_en_attente": sum(
            1
            for p in assistance.propositions
            if p.statut == StatutProposition.en_attente
        ),
    }


@router.get("/assistance/{assistance_id}", response_model=AssistanceOut)
async def get_assistance(
    assistance_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DemandeAssistance)
        .options(*_load_propositions_options())
        .where(DemandeAssistance.id == assistance_id)
    )
    assistance = result.scalar_one_or_none()
    if not assistance:
        raise HTTPException(status_code=404, detail="Demande non trouvée")

    profil = (
        await _profil_mecanicien_of(db, current_user.id)
        if current_user.role == UserRole.mecanicien
        else None
    )
    d_lat, d_lng = _parse_wkt(assistance.localisation)
    dist = None
    if profil is not None and (d_lat, d_lng) != (0.0, 0.0):
        p_lat, p_lng = _parse_wkt(profil.localisation)
        if (p_lat, p_lng) != (0.0, 0.0):
            dist = round(_haversine(d_lat, d_lng, p_lat, p_lng), 1)
    return _assistance_out(
        assistance, distance_km=dist, profil_mecanicien=profil
    )


@router.put("/assistance/{assistance_id}/statut")
async def update_assistance_statut(
    assistance_id: uuid.UUID,
    data: AssistanceUpdateStatut,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DemandeAssistance)
        .options(*_load_propositions_options())
        .where(DemandeAssistance.id == assistance_id)
    )
    assistance = result.scalar_one_or_none()
    if not assistance:
        raise HTTPException(status_code=404, detail="Demande non trouvée")

    # ── Permissions strictes ──
    # - l'administrateur peut tout faire ;
    # - seul le mécanicien ASSIGNÉ (après sélection par le chauffeur) peut
    #   faire avancer l'intervention (en_cours / terminee) ;
    # - un mécanicien non sélectionné, un chauffeur ou un tiers ne peuvent PAS
    #   modifier le statut (test : « un mécanicien rejeter essaie de changer
    #   son statut » / « un mécanicien essaie d'accepter à la place du
    #   chauffeur » → refusé par le backend).
    if current_user.role == UserRole.admin:
        pass
    elif current_user.role == UserRole.mecanicien:
        profil_result = await db.execute(
            select(ProfilMecanicien).where(ProfilMecanicien.user_id == current_user.id)
        )
        profil = profil_result.scalar_one_or_none()
        if (
            not profil
            or not assistance.mecanicien_id
            or str(profil.id) != str(assistance.mecanicien_id)
        ):
            raise HTTPException(
                status_code=403,
                detail="Seul le mécanicien sélectionné par le chauffeur peut modifier le statut",
            )
        if assistance.statut == StatutAssistance.en_attente:
            raise HTTPException(
                status_code=400,
                detail="Le chauffeur n'a pas encore sélectionné de mécanicien",
            )
    elif not _is_demandeur(current_user, assistance):
        raise HTTPException(status_code=403, detail="Accès non autorisé")

    # Une demande attribuée ne peut jamais revenir en arrière : cela
    # réouvrirait la sélection et casserait la règle « un seul mécanicien ».
    if data.statut in (StatutAssistance.en_attente, StatutAssistance.pris_en_charge):
        if assistance.statut == StatutAssistance.assignee:
            raise HTTPException(
                status_code=400,
                detail="Le mécanicien a déjà été sélectionné : retour en arrière impossible",
            )

    assistance.statut = data.statut
    await db.flush()

    # ── Module 3 : prévenir le demandeur quand l'intervention est terminée.
    if data.statut == "terminee" and assistance.demandeur_id:
        from app.assistance_events import broadcast_assistance_event
        from app.utils.notifications import notify_user

        await broadcast_assistance_event(
            {"type": "assistance_taken", "demande_id": str(assistance_id)}
        )
        await notify_user(
            db,
            user_id=assistance.demandeur_id,
            titre="Intervention terminée",
            contenu="Votre demande d'assistance a été marquée comme réparée par le mécanicien.",
            type_notif="assistance",
            lien="/dashboard/chauffeur/assistance",
            metadata={"demande_id": str(assistance_id)},
            email=True,
            push=True,
        )

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
