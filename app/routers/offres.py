import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.offre import OffreRecrutement
from app.models.candidature import Candidature
from app.models.proprietaire import ProfilProprietaire
from app.routers.auth import get_current_user
from app.utils.notifications import notify_user

router = APIRouter(prefix="/api/offres", tags=["Offres"])

EDIT_WINDOW_MINUTES = 5
OFFRE_EXPIRATION_DAYS = 30


def _is_editable(created_at) -> bool:
    if not created_at:
        return False
    now = datetime.now(timezone.utc)
    created = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at
    return (now - created) <= timedelta(minutes=EDIT_WINDOW_MINUTES)


def _is_expired(expires_at) -> bool:
    if not expires_at:
        return False
    now = datetime.now(timezone.utc)
    exp = expires_at.replace(tzinfo=timezone.utc) if expires_at.tzinfo is None else expires_at
    return now > exp


async def _offre_out(o: OffreRecrutement, db: AsyncSession) -> dict:
    proprietaire_info = None
    try:
        profil_result = await db.execute(
            select(ProfilProprietaire).where(ProfilProprietaire.id == o.proprietaire_id)
        )
        profil = profil_result.scalar_one_or_none()
        if profil:
            user_result = await db.execute(
                select(User).where(User.id == profil.user_id)
            )
            user = user_result.scalar_one_or_none()
            if user:
                proprietaire_info = {
                    "nom_complet": user.nom_complet,
                    "nom_entreprise": profil.nom_entreprise,
                    "photo_profil": user.photo_profil,
                    "telephone": user.telephone,
                }
    except Exception:
        pass

    expired = _is_expired(o.expires_at)

    return {
        "id": str(o.id),
        "proprietaire_id": str(o.proprietaire_id),
        "proprietaire_info": proprietaire_info,
        "titre": o.titre,
        "description": o.description,
        "type_contrat": o.type_contrat.value if hasattr(o.type_contrat, "value") else o.type_contrat,
        "salaire_propose": o.salaire_propose,
        "zone_travail": o.zone_travail,
        "date_debut": str(o.date_debut),
        "camion_id": str(o.camion_id) if o.camion_id else None,
        "statut": "expirée" if expired else (o.statut.value if hasattr(o.statut, "value") else o.statut),
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "expires_at": o.expires_at.isoformat() if o.expires_at else None,
        "is_editable": _is_editable(o.created_at) and not expired,
        "is_expired": expired,
    }


@router.get("/")
async def list_offres(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    type_contrat: str | None = None,
    zone: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    query = select(OffreRecrutement).where(
        OffreRecrutement.statut == "active",
        (OffreRecrutement.expires_at.is_(None)) | (OffreRecrutement.expires_at > now),
    )
    if type_contrat:
        query = query.where(OffreRecrutement.type_contrat == type_contrat)
    if zone:
        query = query.where(OffreRecrutement.zone_travail.ilike(f"%{zone}%"))
    query = query.order_by(OffreRecrutement.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    offres = result.scalars().all()
    return [await _offre_out(o, db) for o in offres]


@router.get("/{offre_id}")
async def get_offre(offre_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(OffreRecrutement).where(OffreRecrutement.id == offre_id)
    )
    offre = result.scalar_one_or_none()
    if not offre:
        raise HTTPException(status_code=404, detail="Offre non trouvée")
    return await _offre_out(offre, db)


@router.post("/{offre_id}/candidater")
async def postuler_offre(
    offre_id: uuid.UUID,
    body: dict = {},
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role.value != "chauffeur":
        raise HTTPException(status_code=403, detail="Réservé aux chauffeurs")

    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=422, detail="Un message d'accompagnement est obligatoire")

    result = await db.execute(
        select(OffreRecrutement).where(OffreRecrutement.id == offre_id)
    )
    offre = result.scalar_one_or_none()
    if not offre:
        raise HTTPException(status_code=404, detail="Offre non trouvée")

    expired = _is_expired(offre.expires_at)
    if expired:
        raise HTTPException(status_code=400, detail="Cette offre a expiré")

    existing = await db.execute(
        select(Candidature).where(
            Candidature.offre_id == str(offre_id),
            Candidature.chauffeur_id == str(current_user.id),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Vous avez déjà postulé à cette offre")

    candidature = Candidature(
        id=uuid.uuid4(),
        offre_id=str(offre_id),
        chauffeur_id=str(current_user.id),
        message=message,
        statut="en_attente",
    )
    db.add(candidature)

    conversation_id = None
    profil_result = await db.execute(
        select(ProfilProprietaire).where(ProfilProprietaire.id == offre.proprietaire_id)
    )
    profil = profil_result.scalar_one_or_none()
    if profil:
        owner_user_id = profil.user_id

        # Ouverture automatique (Module 4) : conversation privée entre le
        # candidat et le propriétaire, réutilisée si elle existe déjà.
        from app.routers.conversations import get_or_create_direct_conversation
        from app.models.message import Message

        conv = await get_or_create_direct_conversation(db, current_user.id, owner_user_id)
        conversation_id = str(conv.id)

        db.add(
            Message(
                id=uuid.uuid4(),
                conversation_id=conv.id,
                expediteur_id=current_user.id,
                contenu=message,
                type="texte",
            )
        )
        conv.updated_at = datetime.now(timezone.utc)

        await notify_user(
            db,
            user_id=profil.user_id,
            titre="Nouvelle candidature reçue",
            contenu=f"{current_user.nom_complet} a postulé à votre offre « {offre.titre} ».",
            type_notif="admin",
            lien=f"/dashboard/chat?conv={conversation_id}",
            metadata={"conversation_id": conversation_id, "offre_id": str(offre_id)},
            email=True,
            push=True,
        )

    await notify_user(
        db,
        user_id=current_user.id,
        titre="Candidature envoyée",
        contenu=f"Votre candidature à l'offre « {offre.titre} » a été envoyée avec succès.",
        type_notif="admin",
        lien=f"/dashboard/chauffeur/offres",
    )

    await db.flush()
    return {
        "message": "Candidature envoyée avec succès",
        "id": str(candidature.id),
        "conversation_id": conversation_id,
    }


@router.get("/{offre_id}/mes-candidatures")
async def mes_candidatures(
    offre_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Candidature).where(
            Candidature.offre_id == str(offre_id),
            Candidature.chauffeur_id == str(current_user.id),
        )
    )
    candidatures = result.scalars().all()
    return [
        {
            "id": str(c.id),
            "offre_id": str(c.offre_id),
            "chauffeur_id": str(c.chauffeur_id),
            "message": c.message,
            "statut": c.statut,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in candidatures
    ]


async def _offre_belongs_to_user(offre: OffreRecrutement, user: User, db: AsyncSession) -> bool:
    """L'utilisateur est-il le propriétaire de l'offre (via son profil) ?"""
    profil = await db.execute(
        select(ProfilProprietaire).where(ProfilProprietaire.id == offre.proprietaire_id)
    )
    p = profil.scalar_one_or_none()
    return bool(p and str(p.user_id) == str(user.id))


@router.get("/{offre_id}/candidatures")
async def list_offre_candidatures(
    offre_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste les candidatures reçues pour une offre. Réservé au propriétaire de
    l'offre (ou à un administrateur).
    """
    if current_user.role.value not in ("proprietaire", "admin"):
        raise HTTPException(status_code=403, detail="Accès réservé au propriétaire de l'offre")

    result = await db.execute(
        select(OffreRecrutement).where(OffreRecrutement.id == offre_id)
    )
    offre = result.scalar_one_or_none()
    if not offre:
        raise HTTPException(status_code=404, detail="Offre non trouvée")

    if not await _offre_belongs_to_user(offre, current_user, db):
        raise HTTPException(status_code=403, detail="Vous n'êtes pas le propriétaire de cette offre")

    candidatures_result = await db.execute(
        select(Candidature, User)
        .join(User, User.id == Candidature.chauffeur_id)
        .where(Candidature.offre_id == str(offre_id))
        .order_by(Candidature.created_at.desc())
    )
    return [
        {
            "id": str(c.id),
            "offre_id": str(offre_id),
            "chauffeur_id": str(chauffeur.id),
            "chauffeur_nom": chauffeur.nom_complet,
            "chauffeur_photo": chauffeur.photo_profil,
            "message": c.message,
            "statut": c.statut,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c, chauffeur in candidatures_result.all()
    ]


@router.put("/{offre_id}/candidatures/{candidature_id}")
async def decide_candidature(
    offre_id: uuid.UUID,
    candidature_id: uuid.UUID,
    body: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Répond à une candidature : `acceptee` (le chauffeur est retenu et l'offre
    est pourvue) ou `refusee`. Réservé au propriétaire de l'offre.
    Le chauffeur est notifié avec un lien vers la conversation privée.
    """
    statut = (body.get("statut") or "").strip().lower()
    if statut not in ("acceptee", "refusee"):
        raise HTTPException(
            status_code=422, detail="Statut invalide (attendu : acceptee ou refusee)"
        )

    offre_result = await db.execute(
        select(OffreRecrutement).where(OffreRecrutement.id == offre_id)
    )
    offre = offre_result.scalar_one_or_none()
    if not offre:
        raise HTTPException(status_code=404, detail="Offre non trouvée")
    if not await _offre_belongs_to_user(offre, current_user, db):
        raise HTTPException(status_code=403, detail="Vous n'êtes pas le propriétaire de cette offre")

    cand_result = await db.execute(
        select(Candidature, User)
        .join(User, User.id == Candidature.chauffeur_id)
        .where(
            Candidature.id == str(candidature_id),
            Candidature.offre_id == str(offre_id),
        )
    )
    row = cand_result.first()
    if not row:
        raise HTTPException(status_code=404, detail="Candidature non trouvée")
    candidature, chauffeur = row

    if candidature.statut != "en_attente":
        raise HTTPException(
            status_code=400, detail="Cette candidature a déjà été traitée"
        )

    candidature.statut = statut
    candidature.updated_at = datetime.now(timezone.utc)

    from app.routers.conversations import get_or_create_direct_conversation
    from app.models.message import Message

    conv = await get_or_create_direct_conversation(db, current_user.id, chauffeur.id)

    if statut == "acceptee":
        # L'offre est pourvue ; les autres candidatures sont refusées.
        offre.statut = "pourvue"
        autres = await db.execute(
            select(Candidature).where(
                Candidature.offre_id == str(offre_id),
                Candidature.id != str(candidature_id),
                Candidature.statut == "en_attente",
            )
        )
        for autre in autres.scalars().all():
            autre.statut = "refusee"
            autre.updated_at = datetime.now(timezone.utc)
        reponse = (
            f"Félicitations {chauffeur.nom_complet} ! Votre candidature à "
            f"« {offre.titre} » a été acceptée. Bienvenue à bord !"
        )
        titre = "Votre candidature a été acceptée"
    else:
        reponse = (
            f"Bonjour {chauffeur.nom_complet}, nous vous remercions d'avoir "
            f"postulé à « {offre.titre} », mais votre candidature n'a pas été retenue."
        )
        titre = "Réponse à votre candidature"

    db.add(
        Message(
            id=uuid.uuid4(),
            conversation_id=conv.id,
            expediteur_id=current_user.id,
            contenu=reponse,
            type="texte",
        )
    )
    conv.updated_at = datetime.now(timezone.utc)

    await notify_user(
        db,
        user_id=chauffeur.id,
        titre=titre,
        contenu=reponse,
        type_notif="admin",
        lien=f"/dashboard/chat?conv={conv.id}",
        metadata={"conversation_id": str(conv.id), "offre_id": str(offre_id), "statut": statut},
        email=True,
        push=True,
    )

    await db.flush()
    return {
        "message": "Réponse envoyée au chauffeur",
        "statut": statut,
        "conversation_id": str(conv.id),
        "offre_pourvue": statut == "acceptee",
    }
