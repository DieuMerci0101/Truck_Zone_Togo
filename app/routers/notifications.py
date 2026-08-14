"""
Router notifications — Module 2 (notifications multi-canal).

Chaque utilisateur authentifié peut :
- Lister ses notifications (avec métadonnées JSON)
- Marquer une/plusieurs notification(s) comme lue(s)
- Compter ses notifications non lues
- Gérer ses préférences de canal (email / push / sms / in_app)
- Abonner / désabonner son navigateur au Web Push (PWA)

Seul un admin peut :
- Créer une notification pour un autre utilisateur
"""

import json
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import delete, select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User
from app.models.notification import Notification
from app.models.notification_preferences import NotificationPreference, PushSubscription
from app.routers.auth import get_current_user, require_admin
from app.schemas.notification import (
    NotificationCreate,
    NotificationOut,
    NotificationPreferencesOut,
    NotificationPreferencesUpdate,
    PushSubscriptionCreate,
    PushSubscriptionOut,
)
from app.utils.notifications import get_preferences

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


def _notification_out(n: Notification) -> NotificationOut:
    data = NotificationOut.model_validate(n)
    if n.metadata_json:
        try:
            data.metadata = json.loads(n.metadata_json)
        except (json.JSONDecodeError, TypeError):
            data.metadata = None
    return data


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
        query = query.where(Notification.lu == False)  # noqa: E712
    query = query.order_by(Notification.created_at.desc()).offset(skip).limit(limit)
    result = await db.execute(query)
    return [_notification_out(n) for n in result.scalars().all()]


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
            Notification.lu == False,  # noqa: E712
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
            Notification.lu == False,  # noqa: E712
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
        metadata_json=json.dumps(data.metadata, ensure_ascii=False) if data.metadata else None,
    )
    db.add(notification)
    await db.flush()
    await db.refresh(notification)
    return _notification_out(notification)


# ─── Préférences de notification ────────────────────────────


@router.get("/preferences", response_model=NotificationPreferencesOut)
async def get_notification_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retourne les préférences de notification de l'utilisateur connecté
    (créées avec les valeurs par défaut si absentes).
    """
    prefs = await get_preferences(db, current_user.id)
    await db.flush()
    return NotificationPreferencesOut(
        user_id=prefs.user_id,
        email=prefs.email,
        push=prefs.push,
        sms=prefs.sms,
        in_app=prefs.in_app,
        updated_at=prefs.updated_at,
    )


@router.put("/preferences", response_model=NotificationPreferencesOut)
async def update_notification_preferences(
    data: NotificationPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Met à jour les préférences de notification (email / push / sms / in_app).
    Seuls les champs envoyés sont modifiés.
    """
    prefs = await get_preferences(db, current_user.id)
    if data.email is not None:
        prefs.email = data.email
    if data.push is not None:
        prefs.push = data.push
    if data.sms is not None:
        prefs.sms = data.sms
    if data.in_app is not None:
        prefs.in_app = data.in_app
    await db.flush()
    await db.refresh(prefs)
    return NotificationPreferencesOut(
        user_id=prefs.user_id,
        email=prefs.email,
        push=prefs.push,
        sms=prefs.sms,
        in_app=prefs.in_app,
        updated_at=prefs.updated_at,
    )


# ─── Web Push (abonnements navigateur) ──────────────────────


@router.post("/push/subscribe", response_model=PushSubscriptionOut, status_code=201)
async def subscribe_to_push(
    data: PushSubscriptionCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Enregistre l'abonnement Web Push du navigateur de l'utilisateur.
    Idempotent : si l'endpoint existe déjà, on renvoie l'existant.
    """
    result = await db.execute(
        select(PushSubscription).where(PushSubscription.endpoint == data.endpoint)
    )
    existing = result.scalar_one_or_none()
    if existing:
        if existing.user_id != current_user.id:
            existing.user_id = current_user.id
            await db.flush()
        return PushSubscriptionOut(
            id=existing.id,
            endpoint=existing.endpoint,
            user_agent=existing.user_agent,
            created_at=existing.created_at,
        )

    sub = PushSubscription(
        id=uuid.uuid4(),
        user_id=current_user.id,
        endpoint=data.endpoint,
        p256dh=data.p256dh,
        auth=data.auth,
        user_agent=request.headers.get("user-agent", "")[:500],
    )
    db.add(sub)
    await db.flush()
    await db.refresh(sub)
    return PushSubscriptionOut(
        id=sub.id,
        endpoint=sub.endpoint,
        user_agent=sub.user_agent,
        created_at=sub.created_at,
    )


@router.delete("/push/subscribe")
async def unsubscribe_from_push(
    data: PushSubscriptionCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Désabonne un appareil (endpoint) du Web Push.
    On supprime l'enregistrement appartenant à l'utilisateur connecté.
    """
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.endpoint == data.endpoint,
            PushSubscription.user_id == current_user.id,
        )
    )
    await db.flush()
    return {"message": "Abonnement push supprimé"}


@router.delete("/push/subscriptions")
async def unsubscribe_all_push(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Désabonne tous les appareils de l'utilisateur (utile à la déconnexion)."""
    await db.execute(
        delete(PushSubscription).where(PushSubscription.user_id == current_user.id)
    )
    await db.flush()
    return {"message": "Tous les abonnements push ont été supprimés"}


@router.get("/push/config")
async def push_config(current_user: User = Depends(get_current_user)):
    """
    Renvoie la clé publique VAPID nécessaire à l'abonnement côté navigateur.
    """
    settings = get_settings()
    return {
        "vapid_public_key": settings.vapid_public_key,
        "active": bool(settings.vapid_public_key and settings.vapid_private_key),
    }
