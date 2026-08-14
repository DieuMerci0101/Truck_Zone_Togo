"""
Module Messagerie — Temps réel via python-socketio.

Événements Socket.io (Togo Truck Connect) :
  connect        : authentification par JWT (rejet si token invalide)
  disconnect     : nettoyage du sid
  join_room      : rejoint la room d'une conversation (vérifie l'appartenance)
  leave_room     : quitte la room d'une conversation
  send_message   : sauvegarde en PostgreSQL PUIS diffuse `receive_message`
  typing         : diffuse l'état « en train d'écrire »
  read_status    : marque les messages comme lus PUIS diffuse l'état de lecture

Serveur monté via ASGIApp (voir `app/socket_app.py`) à côté de FastAPI :
  /socket.io/* → python-socketio (temps réel)
  tout le reste → FastAPI (REST + WebSockets existants)

Confidentialité : un utilisateur ne peut rejoindre/suivre qu'une conversation
dont il est participant (jamais l'admin, jamais un tiers).
"""
import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qs

import socketio  # type: ignore
from sqlalchemy import select
from sqlalchemy.orm import selectinload  # type: ignore

from app.database import async_session
from app.models.conversation import Conversation, ConversationParticipant
from app.models.message import Message
from app.models.user import User

# ─── Serveur Socket.io (ASGI) ───────────────────────
sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins="*",
    logger=False,
    engineio_logger=False,
)

# Mapping sid → user_id (session légère côté serveur).
_SID_TO_USER: dict[str, str] = {}


# ─── Helpers ────────────────────────────────────────
async def _verify_participant(db, conversation_id, user_id) -> bool:
    result = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == str(conversation_id),
            ConversationParticipant.user_id == str(user_id),
        )
    )
    return result.scalar_one_or_none() is not None


async def _compute_recipient(db, conversation_id, sender_id) -> uuid.UUID | None:
    """Destinataire d'une conversation directe : l'autre participant (ou None)."""
    result = await db.execute(
        select(ConversationParticipant).where(
            ConversationParticipant.conversation_id == str(conversation_id)
        )
    )
    parts = [str(p.user_id) for p in result.scalars().all()]
    others = [p for p in parts if p != str(sender_id)]
    return uuid.UUID(others[0]) if others else None


async def _load_fresh_message(db, message_id) -> Message:
    result = await db.execute(
        select(Message)
        .where(Message.id == message_id)
        .options(
            selectinload(Message.expediteur),
            selectinload(Message.reply_to).selectinload(Message.expediteur),
        )
    )
    return result.scalar_one()


async def persist_and_broadcast(
    db,
    conversation_id,
    expediteur_id,
    *,
    contenu: str,
    type: str,
    media_url: str | None = None,
    reply_to_message_id: uuid.UUID | None = None,
    extrait: str | None = None,
) -> dict:
    """
    Sauvegarde un message en PostgreSQL, notifie les autres participants et
    diffuse `receive_message` à toute la room de la conversation (y compris
    l'expéditeur, qui déduplique par `id` côté client).

    Utilisé par l'événement Socket.io `send_message` et par les endpoints REST
    (texte, média, audio) pour garantir un temps réel uniforme.
    """
    from app.routers.conversations import _enrich_message, _notifier_autres_participants

    msg = Message(
        id=uuid.uuid4(),
        conversation_id=conversation_id,
        expediteur_id=expediteur_id,
        destinataire_id=await _compute_recipient(db, conversation_id, expediteur_id),
        contenu=contenu or "",
        type=type,
        media_url=media_url,
        reply_to_message_id=reply_to_message_id,
        lu=False,
    )
    db.add(msg)

    conv_result = await db.execute(
        select(Conversation).where(Conversation.id == conversation_id)
    )
    conv = conv_result.scalar_one_or_none()
    if conv:
        conv.updated_at = datetime.now(timezone.utc)

    await db.flush()

    sender_result = await db.execute(select(User).where(User.id == expediteur_id))
    sender = sender_result.scalar_one_or_none()
    await _notifier_autres_participants(
        conversation_id,
        expediteur_id,
        sender.nom_complet if sender else "Utilisateur",
        contenu or "",
        db,
        audio=(type == "audio"),
        extrait=extrait,
    )

    fresh = await _load_fresh_message(db, msg.id)
    payload = _enrich_message(fresh).model_dump(mode="json")
    await sio.emit("receive_message", payload, room=str(conversation_id))
    return payload


# ─── Événements Socket.io ───────────────────────────
@sio.event
async def connect(sid, environ, auth):
    token = None
    if isinstance(auth, dict):
        token = auth.get("token") or auth.get("access_token")
    if not token:
        token = parse_qs(environ.get("QUERY_STRING", "")).get("access_token", [None])[0]
    if not token:
        return False
    try:
        from app.routers.auth import decode_token

        payload = decode_token(token)
        user_id = payload.get("sub")
        if not user_id:
            return False
        async with async_session() as db:
            result = await db.execute(
                select(User).where(
                    User.id == uuid.UUID(user_id),
                    User.is_active.is_(True),
                )
            )
            if result.scalar_one_or_none() is None:
                return False
        _SID_TO_USER[sid] = str(user_id)
        return True
    except Exception:
        return False


@sio.event
async def disconnect(sid):
    _SID_TO_USER.pop(sid, None)


@sio.event
async def join_room(sid, data):
    user_id = _SID_TO_USER.get(sid)
    conversation_id = (data or {}).get("conversation_id")
    if not user_id or not conversation_id:
        return {"error": "Paramètres manquants"}
    async with async_session() as db:
        if not await _verify_participant(db, conversation_id, user_id):
            return {"error": "Accès refusé sur cette conversation"}
    await sio.enter_room(sid, str(conversation_id))
    return {"ok": True}


@sio.event
async def leave_room(sid, data):
    conversation_id = (data or {}).get("conversation_id")
    if conversation_id:
        await sio.leave_room(sid, str(conversation_id))
    return {"ok": True}


@sio.event
async def send_message(sid, data):
    user_id = _SID_TO_USER.get(sid)
    conversation_id = (data or {}).get("conversation_id")
    contenu = (data.get("contenu") or "").strip()
    reply_to_message_id = (data or {}).get("reply_to_message_id")

    if not user_id or not conversation_id or not contenu:
        return {"error": "Paramètres manquants"}
    if len(contenu) > 5000:
        return {"error": "Message trop long (5000 caractères max)"}

    reply_uuid = None
    if reply_to_message_id:
        try:
            reply_uuid = uuid.UUID(str(reply_to_message_id))
        except (ValueError, TypeError):
            return {"error": "Message référencé invalide"}

    async with async_session() as db:
        if not await _verify_participant(db, conversation_id, user_id):
            return {"error": "Accès refusé sur cette conversation"}

        if reply_uuid is not None:
            ref_result = await db.execute(
                select(Message).where(
                    Message.id == reply_uuid,
                    Message.conversation_id == str(conversation_id),
                )
            )
            if ref_result.scalar_one_or_none() is None:
                return {"error": "Message référencé introuvable dans cette conversation"}

        try:
            payload = await persist_and_broadcast(
                db,
                str(conversation_id),
                user_id,
                contenu=contenu,
                type="texte",
                media_url=None,
                reply_to_message_id=reply_uuid,
            )
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return {"ok": True, "message": payload}


@sio.event
async def typing(sid, data):
    user_id = _SID_TO_USER.get(sid)
    conversation_id = (data or {}).get("conversation_id")
    if not user_id or not conversation_id:
        return
    await sio.emit(
        "typing",
        {
            "conversation_id": str(conversation_id),
            "user_id": user_id,
            "is_typing": bool((data or {}).get("is_typing")),
        },
        room=str(conversation_id),
        skip_sid=sid,
    )


@sio.event
async def read_status(sid, data):
    user_id = _SID_TO_USER.get(sid)
    conversation_id = (data or {}).get("conversation_id")
    if not user_id or not conversation_id:
        return
    async with async_session() as db:
        if not await _verify_participant(db, conversation_id, user_id):
            return
        result = await db.execute(
            select(Message).where(
                Message.conversation_id == str(conversation_id),
                Message.expediteur_id != str(user_id),
                Message.lu == False,  # noqa: E712
            )
        )
        unread = result.scalars().all()
        for m in unread:
            m.lu = True
        await db.commit()

    await sio.emit(
        "read_status",
        {
            "conversation_id": str(conversation_id),
            "reader_id": str(user_id),
        },
        room=str(conversation_id),
        skip_sid=sid,
    )
