"""
Vue d'ensemble du tableau de bord — un seul appel par rôle.

Endpoint léger et structuré : pensé pour alimenter à la fois les pages web
et une future application mobile native (Android / iOS).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.chauffeur import ProfilChauffeur
from app.models.proprietaire import ProfilProprietaire
from app.models.mecanicien import ProfilMecanicien
from app.models.offre import OffreRecrutement
from app.models.assistance import DemandeAssistance
from app.models.candidature import Candidature
from app.models.camion import Camion
from app.models.notification import Notification
from app.models.message import Message
from app.models.conversation import ConversationParticipant
from app.routers.auth import get_current_user, user_role
from app.schemas.dashboard import CandidatureLeger, DashboardOverview

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

_INTERVENTION_EN_COURS = ("en_attente", "pris_en_charge", "assignee", "en_cours")


async def _non_lues(db: AsyncSession, user_id) -> int:
    return (
        await db.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.destinataire_id == user_id, Notification.lu.is_(False))
        )
    ).scalar() or 0


async def _messages_non_lus(db: AsyncSession, user_id) -> int:
    """Messages reçus non lus dans mes conversations (jamais de contenu ici)."""
    return (
        await db.execute(
            select(func.count())
            .select_from(Message)
            .join(ConversationParticipant, ConversationParticipant.conversation_id == Message.conversation_id)
            .where(
                ConversationParticipant.user_id == user_id,
                Message.expediteur_id != user_id,
                Message.lu.is_(False),
            )
        )
    ).scalar() or 0


def _candidature_leger(c, offre_titre: str | None, chauffeur_nom: str | None) -> CandidatureLeger:
    return CandidatureLeger(
        id=str(c.id),
        offre_titre=offre_titre,
        statut=c.statut,
        chauffeur_nom=chauffeur_nom,
        updated_at=c.updated_at if hasattr(c, "updated_at") and c.updated_at else c.created_at,
    )


async def _overview_chauffeur(db: AsyncSession, user: User) -> dict:
    out = {}
    profil = (
        await db.execute(
            select(ProfilChauffeur).where(ProfilChauffeur.user_id == user.id)
        )
    ).scalar_one_or_none()
    out["disponibilite"] = profil.disponibilite.value if profil and hasattr(profil.disponibilite, "value") else (profil.disponibilite if profil else None)

    # Candidatures du chauffeur
    total_cand = (
        await db.execute(select(func.count()).select_from(Candidature).where(Candidature.chauffeur_id == user.id))
    ).scalar() or 0
    for key, statut in (
        ("candidatures_en_attente", "en_attente"),
        ("candidatures_acceptees", "acceptee"),
        ("candidatures_refusees", "refusee"),
    ):
        out[key] = (
            await db.execute(
                select(func.count()).select_from(Candidature).where(Candidature.chauffeur_id == user.id, Candidature.statut == statut)
            )
        ).scalar() or 0
    out["candidatures_total"] = total_cand

    # Réponses récentes (candidatures traitées par un propriétaire)
    rows = await db.execute(
        select(Candidature, OffreRecrutement)
        .join(OffreRecrutement, OffreRecrutement.id == Candidature.offre_id)
        .where(Candidature.chauffeur_id == user.id, Candidature.statut != "en_attente")
        .order_by(Candidature.updated_at.desc())
        .limit(3)
    )
    out["dernieres_reponses_candidatures"] = [
        _candidature_leger(c, offre.titre, None) for c, offre in rows.all()
    ]

    # Interventions (demandes d'assistance) actives
    out["interventions_actives"] = (
        await db.execute(
            select(func.count())
            .select_from(DemandeAssistance)
            .where(DemandeAssistance.demandeur_id == user.id, DemandeAssistance.statut.in_(_INTERVENTION_EN_COURS))
        )
    ).scalar() or 0
    return out


async def _overview_proprietaire(db: AsyncSession, user: User) -> dict:
    out = {}
    profil = (
        await db.execute(
            select(ProfilProprietaire).where(ProfilProprietaire.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not profil:
        return out

    now = datetime.now(timezone.utc)
    out["offres_actives"] = (
        await db.execute(
            select(func.count())
            .select_from(OffreRecrutement)
            .where(
                OffreRecrutement.proprietaire_id == profil.id,
                OffreRecrutement.statut == "active",
                OffreRecrutement.expires_at > now,
            )
        )
    ).scalar() or 0
    out["camions_publies"] = (
        await db.execute(
            select(func.count())
            .select_from(Camion)
            .where(Camion.proprietaire_id == profil.id, Camion.is_public.is_(True))
        )
    ).scalar() or 0

    # Candidatures reçues sur mes offres
    sub = select(OffreRecrutement.id).where(OffreRecrutement.proprietaire_id == profil.id).subquery()
    out["candidatures_recues"] = (
        await db.execute(
            select(func.count()).select_from(Candidature).where(Candidature.offre_id.in_(sub))
        )
    ).scalar() or 0
    out["candidatures_recues_en_attente"] = (
        await db.execute(
            select(func.count())
            .select_from(Candidature)
            .where(Candidature.offre_id.in_(sub), Candidature.statut == "en_attente")
        )
    ).scalar() or 0

    rows = await db.execute(
        select(Candidature, OffreRecrutement, User)
        .join(OffreRecrutement, OffreRecrutement.id == Candidature.offre_id)
        .join(User, User.id == Candidature.chauffeur_id)
        .where(Candidature.offre_id.in_(sub))
        .order_by(Candidature.created_at.desc())
        .limit(5)
    )
    out["dernieres_candidatures_recues"] = [
        _candidature_leger(c, offre.titre, chauffeur.nom_complet) for c, offre, chauffeur in rows.all()
    ]

    out["interventions_actives"] = (
        await db.execute(
            select(func.count())
            .select_from(DemandeAssistance)
            .where(DemandeAssistance.demandeur_id == user.id, DemandeAssistance.statut.in_(_INTERVENTION_EN_COURS))
        )
    ).scalar() or 0
    return out


async def _overview_mecanicien(db: AsyncSession, user: User) -> dict:
    out = {}
    profil = (
        await db.execute(
            select(ProfilMecanicien).where(ProfilMecanicien.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not profil:
        return out
    out["disponibilite"] = profil.disponibilite.value if hasattr(profil.disponibilite, "value") else profil.disponibilite
    out["position_active"] = bool(profil.position_active)

    # Demandes d'assistance disponibles (file « premier arrivé »)
    out["demandes_disponibles"] = (
        await db.execute(
            select(func.count()).select_from(DemandeAssistance).where(DemandeAssistance.statut == "en_attente")
        )
    ).scalar() or 0

    # Mes interventions
    out["interventions_actives"] = (
        await db.execute(
            select(func.count())
            .select_from(DemandeAssistance)
            .where(DemandeAssistance.mecanicien_id == profil.id, DemandeAssistance.statut.in_(_INTERVENTION_EN_COURS))
        )
    ).scalar() or 0
    out["interventions_terminees"] = (
        await db.execute(
            select(func.count())
            .select_from(DemandeAssistance)
            .where(DemandeAssistance.mecanicien_id == profil.id, DemandeAssistance.statut == "terminee")
        )
    ).scalar() or 0
    return out


@router.get("/overview", response_model=DashboardOverview)
async def dashboard_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Vue d'ensemble de l'utilisateur connecté, adaptée à son rôle.

    - chauffeur : disponibilité, réponses aux candidatures, interventions.
    - proprietaire : offres actives, camions publiés, candidatures reçues.
    - mecanicien : position active, demandes disponibles, interventions.
    - admin : agrégats globaux (voir /api/admin/stats), sans accès au
      contenu des conversations privées.
    """
    role = user_role(current_user)
    base = {
        "role": role,
        "date": datetime.now(timezone.utc),
        "statut_verification": current_user.verification_status or "pending_upload",
        "is_verified": bool(current_user.is_verified),
        "notifications_non_lues": await _non_lues(db, current_user.id),
        "messages_non_lus": await _messages_non_lus(db, current_user.id),
    }

    if role == "admin":
        from app.services.stats import admin_stats
        base["stats"] = await admin_stats(db)
    elif role == "chauffeur":
        base.update(await _overview_chauffeur(db, current_user))
    elif role == "proprietaire":
        base.update(await _overview_proprietaire(db, current_user))
    elif role == "mecanicien":
        base.update(await _overview_mecanicien(db, current_user))

    return DashboardOverview(**base)
