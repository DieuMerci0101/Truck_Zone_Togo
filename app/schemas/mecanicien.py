import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator


def parse_localisation(loc: str | None) -> tuple[Optional[float], Optional[float]]:
    """Parse WKT POINT string to (lat, lng)."""
    if not loc:
        return None, None
    try:
        coords = loc.replace("POINT(", "").replace(")", "").split()
        lng, lat = float(coords[0]), float(coords[1])
        return lat, lng
    except (ValueError, IndexError):
        return None, None


# ─── Profil Mécanicien ─────────────────────────────

class ProfilMecanicienCreate(BaseModel):
    specialites: list[str]
    annees_experience: int = Field(..., ge=0)
    certifications: Optional[list[str]] = None
    tarification: str = Field(..., pattern=r"^(Gratuit|Payant|Sur devis)$")
    localisation_lat: float = Field(..., ge=-90, le=90)
    localisation_lng: float = Field(..., ge=-180, le=180)
    rayon_intervention: int = Field(..., gt=0)
    bio: Optional[str] = None


class ProfilMecanicienUpdate(BaseModel):
    specialites: Optional[list[str]] = None
    annees_experience: Optional[int] = Field(None, ge=0)
    certifications: Optional[list[str]] = None
    tarification: Optional[str] = None
    localisation_lat: Optional[float] = Field(None, ge=-90, le=90)
    localisation_lng: Optional[float] = Field(None, ge=-180, le=180)
    rayon_intervention: Optional[int] = Field(None, gt=0)
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    disponibilite: Optional[str] = None


class ProfilMecanicienOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    specialites: list[str]
    annees_experience: int
    certifications: Optional[list[str]] = None
    tarification: str
    disponibilite: str
    localisation_lat: Optional[float] = None
    localisation_lng: Optional[float] = None
    rayon_intervention: int
    bio: Optional[str] = None
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


# ─── Demande d'assistance ──────────────────────────

class AssistanceCreate(BaseModel):
    type_panne: str = Field(..., pattern=r"^(Mécanique|Pneumatique|Électricité|Carrosserie|Autre)$")
    description: str
    urgence: str = Field(..., pattern=r"^(Faible|Moyenne|Haute|Critique)$")
    localisation_lat: float = Field(..., ge=-90, le=90)
    localisation_lng: float = Field(..., ge=-180, le=180)
    vehicule_description: str = Field(..., max_length=255)


class AssistanceUpdateStatut(BaseModel):
    statut: str = Field(..., pattern=r"^(en_attente|assignee|en_cours|terminee)$")


class AssistanceOut(BaseModel):
    id: uuid.UUID
    demandeur_id: uuid.UUID
    mecanicien_id: Optional[uuid.UUID] = None
    type_panne: str
    description: str
    urgence: str
    vehicule_description: str
    statut: str
    created_at: datetime

    model_config = {"from_attributes": True}
