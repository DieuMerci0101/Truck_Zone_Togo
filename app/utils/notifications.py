"""
Notification multi-canal.

À chaque événement pertinent (nouveau message, demande d'assistance, offre
publiée, changement de statut...) :

1. `notify_user` enregistre TOUJOURS la notification en base (badge « Non lu »
   au prochain login).
2. Selon les PRÉFÉRENCES de l'utilisateur (`notification_preferences`), elle
   envoie en plus :
   - un e-mail (via l'API Brevo, port 443),
   - une notification Web Push (PWA) si le navigateur est abonné,
   - un SMS de secours (uniquement pour les urgences : assistance, sécurité).

Aucun canal externe configuré (VAPID, SMS) = simple log, jamais d'échec.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.enums import UserRole
from app.models.notification import Notification
from app.models.notification_preferences import NotificationPreference, PushSubscription
from app.models.user import User

logger = logging.getLogger(__name__)


# ─── Préférences utilisateur ─────────────────────────────────


async def get_preferences(db: AsyncSession, user_id: uuid.UUID) -> NotificationPreference:
    """Retourne les préférences de l'utilisateur, créées avec les défauts si absent."""
    result = await db.execute(
        select(NotificationPreference).where(NotificationPreference.user_id == user_id)
    )
    prefs = result.scalar_one_or_none()
    if prefs is None:
        prefs = NotificationPreference(user_id=user_id)
        db.add(prefs)
        await db.flush()
    return prefs


# ─── Enregistrement en base ──────────────────────────────────


async def create_notification(
    db: AsyncSession,
    destinataire_id: uuid.UUID,
    titre: str,
    contenu: str,
    type_notif: str = "systeme",
    lien: str | None = None,
    metadata: dict | None = None,
) -> Notification:
    """Enregistre une notification en base (toujours, quel que soit le canal)."""
    notification = Notification(
        id=uuid.uuid4(),
        destinataire_id=destinataire_id,
        titre=titre,
        contenu=contenu,
        type=type_notif,
        lien=lien,
        metadata_json=json.dumps(metadata, ensure_ascii=False) if metadata else None,
    )
    db.add(notification)
    return notification


async def notify_all_admins(
    db: AsyncSession,
    titre: str,
    contenu: str,
    type_notif: str = "admin",
    lien: str | None = None,
    metadata: dict | None = None,
) -> list[Notification]:
    result = await db.execute(
        select(User).where(User.role == UserRole.admin, User.is_active == True)  # noqa: E712
    )
    admins = result.scalars().all()
    notifications = []
    for admin in admins:
        n = await create_notification(
            db,
            destinataire_id=admin.id,
            titre=titre,
            contenu=contenu,
            type_notif=type_notif,
            lien=lien,
            metadata=metadata,
        )
        notifications.append(n)
    return notifications


# ─── Envoi e-mail (via API Brevo) ────────────────────────────


async def _send_email(channels_email: str, titre: str, contenu: str) -> None:
    """Envoie un email court de notification. Non bloquant pour l'appelant."""
    from app.utils.email import EmailSendError, send_email_in_thread, send_simple_notification_email

    try:
        await send_email_in_thread(
            send_simple_notification_email, channels_email, titre, contenu
        )
    except EmailSendError as exc:
        logger.warning("[NOTIF] Email non envoyé à %s : %s", channels_email, exc)


# ─── Web Push (PWA) ──────────────────────────────────────────


async def send_webpush(
    db: AsyncSession,
    user_id: uuid.UUID,
    titre: str,
    contenu: str,
    lien: str | None = None,
) -> None:
    """Envoie la notification à tous les appareils abonnés de l'utilisateur."""
    settings = get_settings()
    if not (settings.vapid_public_key and settings.vapid_private_key):
        logger.info("[NOTIF] Web Push ignoré : VAPID non configuré.")
        return

    result = await db.execute(
        select(PushSubscription).where(PushSubscription.user_id == user_id)
    )
    subs = result.scalars().all()
    if not subs:
        return

    from app.services.push import send_push_payload

    payload = {"title": titre, "body": contenu, "url": lien, "type": "notification"}
    for sub in subs:
        try:
            await asyncio.to_thread(
                send_push_payload, sub, payload, settings
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("[NOTIF] Push échoué pour %s : %s", sub.endpoint[:60], exc)


# ─── SMS (secours urgence, API Brevo) ────────────────────────


async def send_sms(phone: str, contenu: str) -> None:
    """Envoie un SMS transactionnel Brevo. Ignoré si non configuré / crédits absents."""
    settings = get_settings()
    if not settings.brevo_api_key:
        logger.info("[NOTIF] SMS ignoré : BREVO_API_KEY non défini.")
        return
    if not phone:
        logger.warning("[NOTIF] SMS ignoré : aucun numéro pour le destinataire.")
        return
    if not phone.startswith("+"):
        phone = f"+{phone.lstrip('0')}"

    body = {
        "type": "transactional",
        "unicodeEnabled": True,
        "sender": settings.sms_sender,
        "recipient": phone,
        "content": contenu,
    }
    headers = {
        "accept": "application/json",
        "api-key": settings.brevo_api_key,
        "content-type": "application/json",
    }
    try:
        resp = await asyncio.to_thread(
            httpx.post,
            "https://api.brevo.com/v3/transactionalSMS/sms",
            json=body,
            headers=headers,
            timeout=15,
        )
    except Exception as exc:
        logger.warning("[NOTIF] SMS réseau échoué (%s) : %s", phone, exc)
        return
    if resp.status_code >= 400:
        logger.warning("[NOTIF] SMS refusé (%s) : %s", phone, resp.text[:200])


# ─── Dispatch multi-canal ────────────────────────────────────


async def notify_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    titre: str,
    contenu: str,
    type_notif: str = "systeme",
    lien: str | None = None,
    metadata: dict | None = None,
    *,
    email: bool = False,
    push: bool = False,
    sms: bool = False,
    urgent: bool = False,
) -> Notification:
    """
    Enregistre la notification en base et la dispatche sur les canaux demandés
    (`email`, `push`, `sms`), chacun soumis à la préférence utilisateur.

    `urgent=True` : force la prise en compte du canal SMS (assistance mécanique,
    sécurité) — le SMS est un canal de secours réservé aux urgences.
    Retourne la notification créée (toujours présente en base).
    """
    prefs = await get_preferences(db, user_id)

    if email and prefs.email:
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user and user.email:
            await _send_email(user.email, titre, contenu)
        else:
            logger.warning("[NOTIF] Email ignoré : aucun email pour user %s", user_id)

    if push and prefs.push:
        await send_webpush(db, user_id, titre, contenu, lien)

    if urgent and sms and prefs.sms:
        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        phone = user.telephone if user else None
        await send_sms(
            phone,
            f"{titre} sur TruckZone Togo. Connectez-vous : "
            f"https://frontend-truck-zone-togo.vercel.app",
        )

    return await create_notification(
        db, user_id, titre, contenu, type_notif, lien, metadata
    )
