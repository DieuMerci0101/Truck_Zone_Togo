import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel # type: ignore


# ─── Document ───────────────────────────────────────

class DocumentOut(BaseModel):
    id: uuid.UUID
    utilisateur_id: uuid.UUID
    type_document: str
    fichier_url: str
    statut: str
    commentaire_admin: Optional[str]
    created_at: datetime
    validated_at: Optional[datetime]

    model_config = {"from_attributes": True}


class DocumentUpdateStatut(BaseModel):
    statut: str  # valide | rejete
    commentaire_admin: Optional[str] = None
