"""
Router notifications — Système de notifications pour tous les utilisateurs.

Chaque utilisateur authentifié peut :
- Lister ses notifications
- Marquer une notification comme lue
- Marquer toutes ses notifications comme lues
- Compter ses notifications non lues

Seul un admin peut :
- Créer une notification pour un autre utilisateur
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.notification import Notification
from app.routers.auth import get_current_user, require_admin
from app.schemas.notification import NotificationCreate, NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("/", response_model=list[NotificationOut])
async def list_notifications(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    non_lues_seulement: bool = False,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Liste les notifications de l'utilisateur connecté.
    Filtrage par lues/non lues possible.
    """
    query = select(Notification).where(Notification.destinataire_id == current_user.id)
    if non_lues_seulement:
        query = query.where(Notification.lu == False)
    query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/non-lues")
async def count_non_lues(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne le nombre de notifications non lues.
    Utile pour afficher un badge dans l'interface.
    """
    result = await db.execute(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.destinataire_id == current_user.id,
            Notification.lu == False,
        )
    )
    count = result.scalar() or 0
    return {"non_lues": count}


@router.put("/{notification_id}/lu")
async def mark_as_read(
    notification_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Marque une notification comme lue.
    Seul le destinataire peut marquer sa propre notification.
    """
    result = await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.destinataire_id == current_user.id,
        )
    )
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification non trouvée")

    notification.lu = True
    await db.flush()
    return {"message": "Notification marquée comme lue"}


@router.put("/tout-lu")
async def mark_all_as_read(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Marque toutes les notifications non lues de l'utilisateur comme lues.
    """
    await db.execute(
        update(Notification)
        .where(
            Notification.destinataire_id == current_user.id,
            Notification.lu == False,
        )
        .values(lu=True)
    )
    await db.flush()
    return {"message": "Toutes les notifications ont été marquées comme lues"}


@router.post("/", response_model=NotificationOut, status_code=201)
async def create_notification(
    data: NotificationCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Crée une notification pour un utilisateur.
    Réservé aux administrateurs.
    """
    destinataire = await db.execute(
        select(User).where(User.id == data.destinataire_id)
    )
    if not destinataire.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Utilisateur destinataire non trouvé")

    notification = Notification(
        id=uuid.uuid4(),
        destinataire_id=data.destinataire_id,
        titre=data.titre,
        contenu=data.contenu,
        type=data.type,
        lien=data.lien,
    )
    db.add(notification)
    await db.flush()
    await db.refresh(notification)
    return notification
