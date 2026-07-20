"""
Module Messagerie — WebSocket temps réel + Redis pub/sub

Comment ça marche :
1. Chaque client se connecte en WebSocket à /ws/chat/{conversation_id}
2. Redis gère le pub/sub pour distribuer les messages entre les instances
3. Les messages sont archivés en PostgreSQL
4. L'indicateur de présence (online/offline) est géré via Redis
"""
import json
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends # type: ignore
from sqlalchemy import select # type: ignore
from sqlalchemy.ext.asyncio import AsyncSession # type: ignore
import redis.asyncio as aioredis # type: ignore

from app.database import get_db, async_session
from app.models.conversation import Conversation, ConversationParticipant
from app.models.message import Message
from app.models.user import User

router = APIRouter()

# ─── Connexion Redis ────────────────────────────────
redis_client: Optional[aioredis.Redis] = None


async def get_redis():
    global redis_client
    if redis_client is None:
        redis_client = aioredis.from_url(
            "redis://localhost:6379/0",
            decode_responses=True,
        )
    return redis_client


# ─── Gestionnaire de connexions WebSocket ──────────
class ConnectionManager:
    """Gère les connexions WebSocket actives."""

    def __init__(self):
        # {conversation_id: {user_id: websocket}}
        self.active_connections: dict[str, dict[str, WebSocket]] = {}

    async def connect(self, websocket: WebSocket, conversation_id: str, user_id: str):
        await websocket.accept()
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = {}
        self.active_connections[conversation_id][user_id] = websocket

        # Marquer l'utilisateur en ligne dans Redis
        r = await get_redis()
        await r.sadd("online_users", user_id)
        await r.publish("presence", json.dumps({"user_id": user_id, "status": "online"}))

    async def disconnect(self, conversation_id: str, user_id: str):
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].pop(user_id, None)
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]

        # Marquer hors ligne
        r = await get_redis()
        await r.srem("online_users", user_id)
        await r.publish("presence", json.dumps({"user_id": user_id, "status": "offline"}))

    async def broadcast(self, conversation_id: str, message: dict, exclude_user: str = None):
        """Envoie un message à tous les membres d'une conversation."""
        if conversation_id in self.active_connections:
            for user_id, ws in self.active_connections[conversation_id].items():
                if user_id != exclude_user:
                    try:
                        await ws.send_json(message)
                    except Exception:
                        pass

        # Publier dans Redis pour les autres instances
        r = await get_redis()
        await r.publish(
            f"chat:{conversation_id}",
            json.dumps(message),
        )


manager = ConnectionManager()


# ─── Endpoint WebSocket ─────────────────────────────
@router.websocket("/ws/chat/{conversation_id}")
async def websocket_chat(websocket: WebSocket, conversation_id: str):
    """
    Endpoint WebSocket pour le chat temps réel.

    Client se connecte avec : ws://localhost:8000/ws/chat/{conversation_id}?token=xxx
    """
    await websocket.accept()

    # Authentification simplifiée (en prod : vérifier le JWT)
    user_id = websocket.query_params.get("user_id", str(uuid.uuid4()))

    await manager.connect(websocket, conversation_id, user_id)

    try:
        while True:
            # Recevoir un message du client
            data = await websocket.receive_json()

            message_type = data.get("type", "texte")

            if message_type == "texte":
                # Sauvegarder en base
                async with async_session() as db:
                    message = Message(
                        id=uuid.uuid4(),
                        conversation_id=conversation_id,
                        expediteur_id=user_id,
                        contenu=data["contenu"],
                        type="texte",
                        lu=False,
                    )
                    db.add(message)

                    # Mettre à jour la conversation
                    result = await db.execute(
                        select(Conversation).where(Conversation.id == conversation_id)
                    )
                    conv = result.scalar_one_or_none()
                    if conv:
                        conv.updated_at = datetime.utcnow()

                    await db.commit()

                # Broadcaster à tous les participants
                await manager.broadcast(
                    conversation_id,
                    {
                        "type": "message",
                        "id": str(message.id),
                        "conversation_id": conversation_id,
                        "expediteur_id": user_id,
                        "contenu": data["contenu"],
                        "message_type": "texte",
                        "created_at": datetime.utcnow().isoformat(),
                    },
                    exclude_user=user_id,
                )

            elif message_type == "typing":
                # Indicateur "en train d'écrire"
                await manager.broadcast(
                    conversation_id,
                    {
                        "type": "typing",
                        "user_id": user_id,
                        "is_typing": data.get("is_typing", False),
                    },
                    exclude_user=user_id,
                )

            elif message_type == "read":
                # Marquer les messages comme lus
                async with async_session() as db:
                    await db.execute(
                        select(Message).where(
                            Message.conversation_id == conversation_id,
                            Message.expediteur_id != user_id,
                            Message.lu == False,
                        )
                    )
                    # TODO: update lu=True

    except WebSocketDisconnect:
        await manager.disconnect(conversation_id, user_id)


# ─── Présence en ligne ─────────────────────────────
@router.websocket("/ws/presence")
async def websocket_presence(websocket: WebSocket):
    """WebSocket pour suivre la présence en ligne des utilisateurs."""
    await websocket.accept()
    r = await get_redis()
    pubsub = r.pubsub()
    await pubsub.subscribe("presence")

    try:
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True)
            if message:
                await websocket.send_json(json.loads(message["data"]))
    except WebSocketDisconnect:
        await pubsub.unsubscribe("presence")
