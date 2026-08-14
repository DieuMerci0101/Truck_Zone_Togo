import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NotificationCreate(BaseModel):
    destinataire_id: uuid.UUID
    titre: str = Field(..., min_length=1, max_length=255)
    contenu: str = Field(..., min_length=1)
    type: str = Field(default="systeme")
    lien: str | None = None
    metadata: dict | None = None


class NotificationOut(BaseModel):
    id: uuid.UUID
    destinataire_id: uuid.UUID
    titre: str
    contenu: str
    type: str
    lu: bool
    lien: str | None
    metadata: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        # NB: on construit explicitement un dict au lieu de valider l'objet
        # ORM directement : l'ORM expose un attribut SQLAlchemy `metadata`
        # (MetaData) qui entrerait en collision avec le champ pydantic.
        import json

        payload = {
            "id": obj.id,
            "destinataire_id": obj.destinataire_id,
            "titre": obj.titre,
            "contenu": obj.contenu,
            "type": obj.type,
            "lu": obj.lu,
            "lien": obj.lien,
            "created_at": obj.created_at,
        }
        if getattr(obj, "metadata_json", None):
            try:
                payload["metadata"] = json.loads(obj.metadata_json)
            except (json.JSONDecodeError, TypeError):
                payload["metadata"] = None
        return super().model_validate(payload)


class NotificationPreferencesUpdate(BaseModel):
    email: bool | None = None
    push: bool | None = None
    sms: bool | None = None
    in_app: bool | None = None


class NotificationPreferencesOut(BaseModel):
    user_id: uuid.UUID
    email: bool
    push: bool
    sms: bool
    in_app: bool
    updated_at: datetime | None = None


class PushSubscriptionCreate(BaseModel):
    endpoint: str = Field(..., min_length=10, max_length=1024)
    p256dh: str = Field(..., min_length=5, max_length=512)
    auth: str = Field(..., min_length=5, max_length=256)


class PushSubscriptionOut(BaseModel):
    id: uuid.UUID
    endpoint: str
    user_agent: str | None
    created_at: datetime
