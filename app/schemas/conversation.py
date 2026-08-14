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
    # Badge de présence : disponibilité du chauffeur (disponible / en_mission /
    # indisponible) ou statut du mécanicien (en_ligne / hors_ligne).
    presence: Optional[str] = None

    model_config = {"from_attributes": True}


# ─── Conversation ───────────────────────────────────

class ConversationCreate(BaseModel):
    participant_id: uuid.UUID
    premier_message: Optional[str] = None


class InitiateFromOffer(BaseModel):
    camion_id: Optional[uuid.UUID] = None
    offre_id: Optional[uuid.UUID] = None
    message: str = Field(..., min_length=1)


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
    type: str = Field(default="texte", pattern=r"^(texte|image|video|fichier|audio)$")
    reply_to_message_id: Optional[uuid.UUID] = None


class MessageOut(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    expediteur_id: uuid.UUID
    destinataire_id: Optional[uuid.UUID] = None
    contenu: str
    type: str
    media_url: Optional[str] = None
    reply_to_message_id: Optional[uuid.UUID] = None
    # Message d'origine complet (Reply-To), embarqué pour affichage direct.
    reply_to: Optional["MessageOut"] = None
    lu: bool
    created_at: datetime
    expediteur_nom: Optional[str] = None
    expediteur_avatar: Optional[str] = None
    expediteur_role: Optional[str] = None

    model_config = {"from_attributes": True}


MessageOut.model_rebuild()
