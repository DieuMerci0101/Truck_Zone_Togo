import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field # type: ignore


# ─── Conversation ───────────────────────────────────

class ConversationCreate(BaseModel):
    participant_id: uuid.UUID


class ConversationOut(BaseModel):
    id: uuid.UUID
    type: str
    created_at: datetime
    updated_at: datetime
    last_message: Optional[str] = None
    last_message_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ConversationParticipantOut(BaseModel):
    user_id: uuid.UUID
    nom_complet: str
    photo_url: Optional[str] = None
    is_online: bool = False


# ─── Message ────────────────────────────────────────

class MessageCreate(BaseModel):
    contenu: str = Field(..., min_length=1)
    type: str = Field(default="texte", pattern=r"^(texte|image|fichier)$")


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    expediteur_id: uuid.UUID
    contenu: str
    type: str
    lu: bool
    created_at: datetime

    model_config = {"from_attributes": True}
