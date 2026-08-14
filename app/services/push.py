"""Envoi de notifications Web Push (PWA) aux navigateurs abonnés."""
from __future__ import annotations

import base64
import logging

from app.config import Settings
from app.models.notification_preferences import PushSubscription

logger = logging.getLogger(__name__)


def _resolve_private_key(value: str) -> str:
    """
    La clé privée VAPID est stockée en une ligne : soit PEM brut
    (généré par py_vapid), soit base64 du PEM (pour les .env mono-ligne).
    """
    value = value.strip()
    if value.startswith("-----BEGIN"):
        return value
    try:
        return base64.b64decode(value).decode()
    except Exception:
        return value


def send_push_payload(
    subscription: PushSubscription,
    payload: dict,
    settings: Settings,
) -> None:
    """
    Envoie `payload` (JSON : title, body, url) à un abonnement Web Push donné.
    Doit tourner dans un thread (`asyncio.to_thread`) : I/O réseau bloquant.
    """
    from pywebpush import WebPushException, webpush

    subscription_info = {
        "endpoint": subscription.endpoint,
        "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
    }
    vapid_private_key = _resolve_private_key(settings.vapid_private_key)
    vapid_claims = {"sub": settings.vapid_subject}

    try:
        webpush(
            subscription_info=subscription_info,
            data=payload,
            vapid_private_key=vapid_private_key,
            vapid_claims=vapid_claims,
            timeout=10,
        )
        logger.info("[PUSH] Notification envoyée à %s", subscription.endpoint[:60])
    except WebPushException as exc:
        if getattr(exc, "response", None) is not None and exc.response.status_code in (
            404,
            410,
        ):
            # L'abonnement n'existe plus (appareil désinstallé / désabonné).
            # Le nettoyage est effectué côté routeur ; on journalise ici.
            logger.warning(
                "[PUSH] Abonnement expiré (HTTP %s) : %s",
                exc.response.status_code,
                subscription.endpoint[:60],
            )
            raise
        logger.error("[PUSH] Erreur d'envoi : %s", exc)
    except Exception as exc:  # noqa: BLE001
        logger.error("[PUSH] Erreur inattendue : %s", exc)
