"""
Router admin — Toutes les routes de ce fichier sont réservées aux administrateurs.

Chaque endpoint utilise la dependency `require_admin` qui vérifie :
1. Que l'utilisateur est authentifié (token JWT valide)
2. Que le rôle de l'utilisateur est bien "admin"
3. Sinon, renvoie une erreur HTTP 403 (Accès interdit)

Utilisation :
    from app.routers.auth import require_admin

    @router.get("/admin/users")
    async def list_users(admin: User = Depends(require_admin)):
        ...
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.chauffeur import ProfilChauffeur
from app.models.proprietaire import ProfilProprietaire
from app.models.mecanicien import ProfilMecanicien
from app.models.incident import Incident
from app.routers.auth import require_admin

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ─── Statistiques du dashboard ─────────────────────

@router.get("/stats")
async def get_stats(
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne les statistiques globales pour le dashboard admin.
    Protégé : uniquement les administrateurs.
    """
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar() or 0
    total_chauffeurs = (
        await db.execute(
            select(func.count()).select_from(User).where(User.role == "chauffeur")
        )
    ).scalar() or 0
    total_proprietaires = (
        await db.execute(
            select(func.count()).select_from(User).where(User.role == "proprietaire")
        )
    ).scalar() or 0
    total_mecaniciens = (
        await db.execute(
            select(func.count()).select_from(User).where(User.role == "mecanicien")
        )
    ).scalar() or 0
    total_admins = (
        await db.execute(
            select(func.count()).select_from(User).where(User.role == "admin")
        )
    ).scalar() or 0

    return {
        "total_utilisateurs": total_users,
        "chauffeurs": total_chauffeurs,
        "proprietaires": total_proprietaires,
        "mecaniciens": total_mecaniciens,
        "admins": total_admins,
    }


# ─── Gestion des utilisateurs ──────────────────────

@router.get("/users")
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    role: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste tous les utilisateurs avec filtres optionnels.
    Protégé : uniquement les administrateurs.
    """
    query = select(User)
    if role:
        query = query.where(User.role == role)
    query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    users = result.scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "nom_complet": u.nom_complet,
            "telephone": u.telephone,
            "role": u.role.value if hasattr(u.role, "value") else u.role,
            "is_active": u.is_active,
            "is_verified": u.is_verified,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.get("/users/{user_id}")
async def get_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Récupère les détails d'un utilisateur spécifique.
    Protégé : uniquement les administrateurs.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")
    return {
        "id": str(user.id),
        "email": user.email,
        "nom_complet": user.nom_complet,
        "telephone": user.telephone,
        "role": user.role.value if hasattr(user.role, "value") else user.role,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "created_at": user.created_at.isoformat(),
    }


@router.put("/users/{user_id}/status")
async def toggle_user_status(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Active ou désactive un utilisateur.
    Protégé : uniquement les administrateurs.
    """
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé")

    # Un admin ne peut pas se désactiver lui-même
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas désactiver votre propre compte")

    user.is_active = not user.is_active
    await db.flush()
    return {
        "message": f"Utilisateur {'activé' if user.is_active else 'désactivé'} avec succès",
        "is_active": user.is_active,
    }


# ─── Gestion des documents ─────────────────────────

@router.get("/documents")
async def list_all_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    statut: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste tous les documents uploadés par les utilisateurs.
    Protégé : uniquement les administrateurs.
    """
    from app.models.document import Document
    query = select(Document)
    if statut:
        query = query.where(Document.statut == statut)
    query = query.order_by(Document.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    docs = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "utilisateur_id": str(d.utilisateur_id),
            "type_document": d.type_document.value if hasattr(d.type_document, "value") else d.type_document,
            "fichier_url": d.fichier_url,
            "statut": d.statut.value if hasattr(d.statut, "value") else d.statut,
            "created_at": d.created_at.isoformat(),
        }
        for d in docs
    ]


@router.put("/documents/{document_id}/statut")
async def update_document_statut(
    document_id: uuid.UUID,
    statut: str,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Met à jour le statut d'un document (validé, rejeté, en_attente).
    Protégé : uniquement les administrateurs.
    Envoie une notification à l'utilisateur concerné.
    """
    from app.models.document import Document
    from app.utils.notifications import notify_user

    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document non trouvé")
    doc.statut = statut
    doc.validated_at = datetime.now(timezone.utc)

    if statut == "valide":
        await notify_user(
            db,
            user_id=doc.utilisateur_id,
            titre="Document validé",
            contenu=f"Votre document de type « {doc.type_document.value if hasattr(doc.type_document, 'value') else doc.type_document} » a été validé par un administrateur.",
            type_notif="document",
            lien="/dashboard/chauffeur/documents",
        )
        user_result = await db.execute(select(User).where(User.id == doc.utilisateur_id))
        user = user_result.scalar_one_or_none()
        if user:
            user.is_verified = True
    elif statut == "rejete":
        await notify_user(
            db,
            user_id=doc.utilisateur_id,
            titre="Document rejeté",
            contenu=f"Votre document de type « {doc.type_document.value if hasattr(doc.type_document, 'value') else doc.type_document} » a été rejeté. Veuillez recharger un document valide.",
            type_notif="document",
            lien="/dashboard/chauffeur/documents",
        )

    await db.flush()
    return {"message": f"Statut du document mis à jour : {statut}"}


# ─── Gestion des incidents ─────────────────────────

@router.get("/incidents")
async def list_all_incidents(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    statut: str | None = None,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste tous les incidents déclarés.
    Protégé : uniquement les administrateurs.
    """
    from app.models.incident import Incident
    query = select(Incident)
    if statut:
        query = query.where(Incident.statut == statut)
    query = query.order_by(Incident.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    incidents = result.scalars().all()
    return [
        {
            "id": str(i.id),
            "declarant_id": str(i.declarant_id),
            "type_incident": i.type_incident.value if hasattr(i.type_incident, "value") else i.type_incident,
            "date_incident": i.date_incident.isoformat() if i.date_incident else None,
            "description": i.description,
            "gravite": i.gravite.value if hasattr(i.gravite, "value") else i.gravite,
            "statut": i.statut.value if hasattr(i.statut, "value") else i.statut,
            "created_at": i.created_at.isoformat(),
        }
        for i in incidents
    ]
