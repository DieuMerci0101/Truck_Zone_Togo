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
from app.models.conversation import Conversation, ConversationParticipant
from app.routers.auth import get_current_user

router = APIRouter(prefix="/api/offres", tags=["Offres"])

EDIT_WINDOW_MINUTES = 5


def _is_editable(created_at) -> bool:
    if not created_at:
        return False
    now = datetime.now(timezone.utc)
    created = created_at.replace(tzinfo=timezone.utc) if created_at.tzinfo is None else created_at
    return (now - created) <= timedelta(minutes=EDIT_WINDOW_MINUTES)


def _offre_out(o: OffreRecrutement) -> dict:
    return {
        "id": str(o.id),
        "proprietaire_id": str(o.proprietaire_id),
        "titre": o.titre,
        "description": o.description,
        "type_contrat": o.type_contrat.value if hasattr(o.type_contrat, "value") else o.type_contrat,
        "salaire_propose": o.salaire_propose,
        "zone_travail": o.zone_travail,
        "date_debut": str(o.date_debut),
        "camion_id": str(o.camion_id) if o.camion_id else None,
        "statut": o.statut.value if hasattr(o.statut, "value") else o.statut,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "is_editable": _is_editable(o.created_at),
    }


@router.get("/")
async def list_offres(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    type_contrat: str | None = None,
    zone: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    query = select(OffreRecrutement).where(
        OffreRecrutement.statut == "active"
    )
    if type_contrat:
        query = query.where(OffreRecrutement.type_contrat == type_contrat)
    if zone:
        query = query.where(OffreRecrutement.zone_travail.ilike(f"%{zone}%"))
    query = query.order_by(OffreRecrutement.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    offres = result.scalars().all()
    return [_offre_out(o) for o in offres]


@router.get("/{offre_id}")
async def get_offre(offre_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(OffreRecrutement).where(OffreRecrutement.id == offre_id)
    )
    offre = result.scalar_one_or_none()
    if not offre:
        raise HTTPException(status_code=404, detail="Offre non trouvée")
    return _offre_out(offre)


@router.post("/{offre_id}/candidater")
async def postuler_offre(
    offre_id: uuid.UUID,
    body: dict = {},
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role.value != "chauffeur":
        raise HTTPException(status_code=403, detail="Réservé aux chauffeurs")

    result = await db.execute(
        select(OffreRecrutement).where(OffreRecrutement.id == offre_id)
    )
    offre = result.scalar_one_or_none()
    if not offre:
        raise HTTPException(status_code=404, detail="Offre non trouvée")

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
        message=body.get("message", ""),
        statut="en_attente",
    )
    db.add(candidature)

    conversation_id = None
    from app.models.proprietaire import ProfilProprietaire
    profil_result = await db.execute(
        select(ProfilProprietaire).where(ProfilProprietaire.id == offre.proprietaire_id)
    )
    profil = profil_result.scalar_one_or_none()
    if profil:
        owner_user_id = str(profil.user_id)
        conv_check = await db.execute(
            select(ConversationParticipant).join(
                Conversation, ConversationParticipant.conversation_id == Conversation.id
            ).where(
                ConversationParticipant.user_id == current_user.id,
            )
        )
        existing_conv = None
        for cp in conv_check.scalars().all():
            other_cp = await db.execute(
                select(ConversationParticipant).where(
                    ConversationParticipant.conversation_id == cp.conversation_id,
                    ConversationParticipant.user_id == owner_user_id,
                )
            )
            if other_cp.scalar_one_or_none():
                existing_conv = cp.conversation_id
                break

        if existing_conv:
            conversation_id = str(existing_conv)
        else:
            conv = Conversation(type="directe")
            db.add(conv)
            await db.flush()
            db.add(ConversationParticipant(conversation_id=conv.id, user_id=current_user.id))
            db.add(ConversationParticipant(conversation_id=conv.id, user_id=owner_user_id))
            await db.flush()
            conversation_id = str(conv.id)

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
