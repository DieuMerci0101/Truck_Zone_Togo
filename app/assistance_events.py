"""
Événements temps réel des demandes d'assistance — Module 3 (« premier arrivé »).

Un mécanicien connecte son navigateur à `/ws/assistance?user_id=...` ; dès
qu'une demande est créée ou prise en charge, un message lui est poussé et le
frontend rafraîchit instantanément la file d'attente (sans attendre le polling).

Limitation assumée : gestion en mémoire par instance. Render gratuit = 1 seul
web service, donc un seul processus ; pas besoin de Redis ici.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect  # type: ignore

logger = logging.getLogger(__name__)

router = APIRouter()


class AssistanceEventManager:
    def __init__(self) -> None:
        # {user_id: websocket} — un seul onglet par utilisateur.
        self.active: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str) -> None:
        await websocket.accept()
        self.active[user_id] = websocket
        logger.info("[AssistanceWS] connecté : user %s (total %d)", user_id[:8], len(self.active))

    async def disconnect(self, user_id: str) -> None:
        self.active.pop(user_id, None)

    async def broadcast(self, event: dict[str, Any], user_ids: list[str] | None = None) -> None:
        """Pousse `event` à tous les mécaniciens connectés, ou seulement à
        `user_ids` si fournis. Une connexion morte est retirée proprement."""
        targets = {
            uid: ws for uid, ws in self.active.items() if user_ids is None or uid in user_ids
        }
        dead: list[str] = []
        for uid, ws in targets.items():
            try:
                await ws.send_text(json.dumps(event))
            except Exception:  # noqa: BLE001
                dead.append(uid)
        for uid in dead:
            self.active.pop(uid, None)


assistance_manager = AssistanceEventManager()


@router.websocket("/ws/assistance")
async def websocket_assistance(websocket: WebSocket):
    """WebSocket des mécaniciens : reçoit `assistance_new` / `assistance_taken`."""
    user_id = websocket.query_params.get("user_id", "")
    if not user_id:
        await websocket.close(code=1008)
        return

    await assistance_manager.connect(websocket, user_id)

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        await assistance_manager.disconnect(user_id)
    except Exception:  # noqa: BLE001
        await assistance_manager.disconnect(user_id)


async def broadcast_assistance_event(event: dict[str, Any], user_ids: list[str] | None = None) -> None:
    """Point d'entrée pour les routers : pousse un événement assistance."""
    await assistance_manager.broadcast(event, user_ids)
