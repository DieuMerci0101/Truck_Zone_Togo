"""
Point d'entrée ASGI combiné : Socket.io (temps réel) + FastAPI (REST).

L'application FastAPI (`app.main:app`) est désormais déjà encapsulée dans
l'ASGIApp Socket.io (voir `app/main.py`). Ce module fournit un alias
explicite `socket_app` pour lancer le serveur avec :

    uvicorn app.socket_app:socket_app --host 0.0.0.0 --port 8000

- `/socket.io/*`  → python-socketio (messagerie temps réel)
- tout le reste  → l'application FastAPI existante (REST + WebSockets)
"""
from app.main import app

socket_app = app
