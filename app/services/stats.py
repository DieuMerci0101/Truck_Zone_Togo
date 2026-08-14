"""
Statistiques globales (dashboard admin + vue admin mobile).

Toutes les métriques sont des agrégats : les administrateurs n'ont jamais
accès au contenu des conversations privées (seuls des compteurs sont exposés).
"""

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.offre import OffreRecrutement
from app.models.assistance import DemandeAssistance
from app.models.candidature import Candidature
from app.models.camion import Camion
from app.models.document import Document
from app.models.mecanicien import ProfilMecanicien
from app.models.conversation import Conversation, ConversationParticipant
from app.models.message import Message

_VERIF_PENDING = ("pending_upload", "pending_approval")
_INTERVENTION_EN_COURS = ("en_attente", "pris_en_charge", "assignee", "en_cours")


async def _user_counts(db: AsyncSession) -> dict:
    counts = {"total": 0, "actifs": 0, "par_role": {}, "en_attente_verification": 0}
    for role in ("chauffeur", "proprietaire", "mecanicien", "admin"):
        n = (
            await db.execute(select(func.count()).select_from(User).where(User.role == role))
        ).scalar() or 0
        counts["par_role"][role] = n
        counts["total"] += n
    counts["actifs"] = (
        await db.execute(select(func.count()).select_from(User).where(User.is_active.is_(True)))
    ).scalar() or 0
    counts["en_attente_verification"] = (
        await db.execute(
            select(func.count())
            .select_from(User)
            .where(User.verification_status.in_(_VERIF_PENDING))
        )
    ).scalar() or 0
    return counts


async def _offre_counts(db: AsyncSession) -> dict:
    now = datetime.now(timezone.utc)
    total = (await db.execute(select(func.count()).select_from(OffreRecrutement))).scalar() or 0
    actives = (
        await db.execute(
            select(func.count())
            .select_from(OffreRecrutement)
            .where(OffreRecrutement.statut == "active", OffreRecrutement.expires_at > now)
        )
    ).scalar() or 0
    pourvues = (
        await db.execute(
            select(func.count()).select_from(OffreRecrutement).where(OffreRecrutement.statut == "pourvue")
        )
    ).scalar() or 0
    expirees = (
        await db.execute(
            select(func.count()).select_from(OffreRecrutement).where(OffreRecrutement.expires_at <= now)
        )
    ).scalar() or 0
    nouvelles_7j = (
        await db.execute(
            select(func.count())
            .select_from(OffreRecrutement)
            .where(OffreRecrutement.created_at >= now - timedelta(days=7))
        )
    ).scalar() or 0
    return {"total": total, "actives": actives, "pourvues": pourvues, "expirees": expirees, "nouvelles_7j": nouvelles_7j}


async def _intervention_counts(db: AsyncSession) -> dict:
    total = (
        await db.execute(select(func.count()).select_from(DemandeAssistance))
    ).scalar() or 0
    en_attente = (
        await db.execute(
            select(func.count()).select_from(DemandeAssistance).where(DemandeAssistance.statut == "en_attente")
        )
    ).scalar() or 0
    en_cours = (
        await db.execute(
            select(func.count())
            .select_from(DemandeAssistance)
            .where(DemandeAssistance.statut.in_(_INTERVENTION_EN_COURS))
        )
    ).scalar() or 0
    terminees = (
        await db.execute(
            select(func.count()).select_from(DemandeAssistance).where(DemandeAssistance.statut == "terminee")
        )
    ).scalar() or 0
    now = datetime.now(timezone.utc)
    nouvelles_7j = (
        await db.execute(
            select(func.count())
            .select_from(DemandeAssistance)
            .where(DemandeAssistance.created_at >= now - timedelta(days=7))
        )
    ).scalar() or 0
    return {"total": total, "en_attente": en_attente, "en_cours": en_cours, "terminees": terminees, "nouvelles_7j": nouvelles_7j}


async def _document_counts(db: AsyncSession) -> dict:
    docs = (
        await db.execute(
            select(func.count()).select_from(Document).where(Document.statut == "en_attente")
        )
    ).scalar() or 0
    mecaniciens = (
        await db.execute(
            select(func.count())
            .select_from(ProfilMecanicien)
            .where(ProfilMecanicien.verification_status == "pending_approval")
        )
    ).scalar() or 0
    return {"documents": docs, "mecaniciens": mecaniciens, "total": docs + mecaniciens}


async def _candidature_counts(db: AsyncSession) -> dict:
    total = (await db.execute(select(func.count()).select_from(Candidature))).scalar() or 0
    en_attente = (
        await db.execute(select(func.count()).select_from(Candidature).where(Candidature.statut == "en_attente"))
    ).scalar() or 0
    acceptees = (
        await db.execute(select(func.count()).select_from(Candidature).where(Candidature.statut == "acceptee"))
    ).scalar() or 0
    refusees = (
        await db.execute(select(func.count()).select_from(Candidature).where(Candidature.statut == "refusee"))
    ).scalar() or 0
    return {"total": total, "en_attente": en_attente, "acceptees": acceptees, "refusees": refusees}


async def _messagerie_counts(db: AsyncSession) -> dict:
    """Compteurs de messagerie AGRÉGÉS uniquement — jamais le contenu."""
    conversations = (
        await db.execute(select(func.count()).select_from(Conversation))
    ).scalar() or 0
    messages = (
        await db.execute(select(func.count()).select_from(Message))
    ).scalar() or 0
    return {"conversations": conversations, "messages": messages}


def _mois_liste(n: int = 6):
    """Retourne les n derniers mois au format 'AAAA-MM', du plus ancien au plus récent."""
    now = datetime.now(timezone.utc)
    mois = []
    an, m = now.year, now.month
    for _ in range(n):
        mois.append(f"{an:04d}-{m:02d}")
        m -= 1
        if m == 0:
            m = 12
            an -= 1
    return list(reversed(mois))


async def _evolution(db: AsyncSession, model, n: int = 6) -> list[dict]:
    """Répartition par mois de création d'un modèle (mois manquants = 0)."""
    from sqlalchemy import extract

    annee = extract("year", model.created_at)
    mois = extract("month", model.created_at)
    rows = await db.execute(
        select(annee.label("an"), mois.label("m"), func.count().label("n"))
        .group_by(annee, mois)
        .order_by(annee, mois)
    )
    data = {f"{int(r.an):04d}-{int(r.m):02d}": int(r.n) for r in rows.all()}
    return [{"mois": m, "count": data.get(m, 0)} for m in _mois_liste(n)]


async def admin_stats(db: AsyncSession) -> dict:
    """Statistiques complètes du dashboard administrateur."""
    return {
        "utilisateurs": await _user_counts(db),
        "offres": await _offre_counts(db),
        "interventions": await _intervention_counts(db),
        "documents_en_attente": await _document_counts(db),
        "candidatures": await _candidature_counts(db),
        "messagerie": await _messagerie_counts(db),
        "camions": {
            "total": (await db.execute(select(func.count()).select_from(Camion))).scalar() or 0,
            "publics": (
                await db.execute(select(func.count()).select_from(Camion).where(Camion.is_public.is_(True)))
            ).scalar() or 0,
        },
        "evolution": {
            "utilisateurs": await _evolution(db, User),
            "offres": await _evolution(db, OffreRecrutement),
            "interventions": await _evolution(db, DemandeAssistance),
        },
        "calcule_le": datetime.now(timezone.utc).isoformat(),
    }
