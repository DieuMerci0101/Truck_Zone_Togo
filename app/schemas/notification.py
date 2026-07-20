import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NotificationCreate(BaseModel):
    destinataire_id: uuid.UUID
    titre: str = Field(..., min_length=1, max_length=255)
    contenu: str = Field(..., min_length=1)
    type: str = Field(default="systeme")
    lien: str | None = None


class NotificationOut(BaseModel):
    id: uuid.UUID
    destinataire_id: uuid.UUID
    titre: str
    contenu: str
    type: str
    lu: bool
    lien: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
