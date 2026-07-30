import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator # type: ignore


def parse_localisation(loc: str | None) -> tuple[Optional[float], Optional[float]]:
    if not loc:
        return None, None
    try:
        coords = loc.replace("POINT(", "").replace(")", "").split()
        lng, lat = float(coords[0]), float(coords[1])
        return lat, lng
    except (ValueError, IndexError):
        return None, None


class DeclarantInfo(BaseModel):
    id: uuid.UUID
    nom_complet: str
    photo_profil: str | None = None
    role: str


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
    declarant_info: Optional[DeclarantInfo] = None
    type_incident: str
    date_incident: datetime
    description: str
    gravite: str
    vehicules_impliques: Optional[list[str]]
    victimes: bool
    nombre_victimes: Optional[int]
    statut: str
    localisation_lat: Optional[float] = None
    localisation_lng: Optional[float] = None
    photo_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_localisation(cls, data):
        loc = getattr(data, "localisation", None) if hasattr(data, "localisation") else None
        if loc is None and isinstance(data, dict):
            loc = data.get("localisation")
        if loc and not isinstance(loc, str):
            loc = str(loc)
        lat, lng = parse_localisation(loc)
        if isinstance(data, dict):
            data["localisation_lat"] = lat
            data["localisation_lng"] = lng
        else:
            data.localisation_lat = lat
            data.localisation_lng = lng
        return data

    @model_validator(mode="before")
    @classmethod
    def extract_declarant(cls, data):
        declarant = getattr(data, "declarant", None) if hasattr(data, "declarant") else None
        if declarant is None and isinstance(data, dict):
            declarant = data.get("declarant")
        if declarant:
            info = DeclarantInfo(
                id=declarant.id,
                nom_complet=declarant.nom_complet,
                photo_profil=declarant.photo_profil,
                role=declarant.role.value if hasattr(declarant.role, "value") else declarant.role,
            )
            if isinstance(data, dict):
                data["declarant_info"] = info
            else:
                data.declarant_info = info
        return data


class StatutIncidentUpdate(BaseModel):
    statut: str = Field(..., pattern=r"^(declare|en_cours|traite|cloture)$")


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
