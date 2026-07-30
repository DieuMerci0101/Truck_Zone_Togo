import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ─── User info (lightweight, embedded in conversation) ───

class ParticipantOut(BaseModel):
    id: uuid.UUID
    nom_complet: str
    email: str
    telephone: str
    role: str
    photo_profil: Optional[str] = None

    model_config = {"from_attributes": True}


# ─── Conversation ───────────────────────────────────

class ConversationCreate(BaseModel):
    participant_id: uuid.UUID
    premier_message: Optional[str] = None


class ConversationOut(BaseModel):
    id: uuid.UUID
    type: str
    created_at: datetime
    updated_at: datetime
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None
    participants: list[ParticipantOut] = []

    model_config = {"from_attributes": True}


# ─── Message ────────────────────────────────────────

class MessageCreate(BaseModel):
    contenu: str = Field(..., min_length=1)
    type: str = Field(default="texte", pattern=r"^(texte|image|fichier|audio)$")


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    expediteur_id: uuid.UUID
    contenu: str
    type: str
    media_url: Optional[str] = None
    lu: bool
    created_at: datetime
    expediteur_nom: Optional[str] = None
    expediteur_avatar: Optional[str] = None
    expediteur_role: Optional[str] = None

    model_config = {"from_attributes": True}
