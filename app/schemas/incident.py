import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field # type: ignore


# ─── Incident ───────────────────────────────────────

class IncidentCreate(BaseModel):
    type_incident: str = Field(..., pattern=r"^(Accident|Panne|Emboutiillage|Route dégradée|Autre)$")
    date_incident: str  # ISO datetime
    localisation_lat: float = Field(..., ge=-90, le=90)
    localisation_lng: float = Field(..., ge=-180, le=180)
    description: str
    gravite: str = Field(..., pattern=r"^(Faible|Moyenne|Grave|Mortel)$")
    vehicules_impliques: Optional[list[str]] = None
    victimes: bool = False
    nombre_victimes: Optional[int] = Field(None, ge=0)
    temoin_contact: Optional[str] = None


class IncidentUpdate(BaseModel):
    type_incident: Optional[str] = None
    description: Optional[str] = None
    gravite: Optional[str] = None
    victimes: Optional[bool] = None
    nombre_victimes: Optional[int] = Field(None, ge=0)
    statut: Optional[str] = None


class IncidentOut(BaseModel):
    id: uuid.UUID
    declarant_id: uuid.UUID
    type_incident: str
    date_incident: datetime
    description: str
    gravite: str
    vehicules_impliques: Optional[list[str]]
    victimes: bool
    nombre_victimes: Optional[int]
    statut: str
    created_at: datetime

    model_config = {"from_attributes": True}


class IncidentCommentaireCreate(BaseModel):
    contenu: str = Field(..., min_length=1)


class IncidentCommentaireOut(BaseModel):
    id: uuid.UUID
    incident_id: uuid.UUID
    auteur_id: uuid.UUID
    contenu: str
    created_at: datetime

    model_config = {"from_attributes": True}


class IncidentStatistiques(BaseModel):
    total: int
    par_type: dict[str, int]
    par_gravite: dict[str, int]
    par_mois: list[dict]
