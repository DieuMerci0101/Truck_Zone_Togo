import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


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


# ─── Profil Chauffeur ──────────────────────────────

class ProfilChauffeurCreate(BaseModel):
    numero_permis: str = Field(..., max_length=50)
    categorie_permis: str = Field(..., pattern=r"^(C|CE|D)$")
    annees_experience: int = Field(..., ge=0)
    types_transport: list[str]
    zones_circulation: list[str]
    disponibilite: str = Field(default="disponible")
    bio: Optional[str] = None


class ProfilChauffeurUpdate(BaseModel):
    numero_permis: Optional[str] = None
    categorie_permis: Optional[str] = None
    annees_experience: Optional[int] = Field(None, ge=0)
    types_transport: Optional[list[str]] = None
    zones_circulation: Optional[list[str]] = None
    disponibilite: Optional[str] = None
    bio: Optional[str] = None
    photo_url: Optional[str] = None


class UserInfo(BaseModel):
    id: uuid.UUID
    nom_complet: str
    email: str
    telephone: str
    role: str
    photo_profil: Optional[str] = None
    is_active: bool = True
    is_verified: bool = True
    verification_status: Optional[str] = None

    model_config = {"from_attributes": True}


class ProfilChauffeurOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    numero_permis: str
    categorie_permis: str
    annees_experience: int
    types_transport: list[str]
    zones_circulation: list[str]
    disponibilite: str
    bio: Optional[str] = None
    photo_url: Optional[str] = None
    created_at: datetime
    user: Optional[UserInfo] = None

    model_config = {"from_attributes": True}


class DisponibiliteUpdate(BaseModel):
    disponibilite: str = Field(
        ...,
        pattern=r"^(available|on_mission|unavailable|disponible|en_mission|indisponible)$",
    )

    @field_validator("disponibilite")
    @classmethod
    def normaliser_disponibilite(cls, v: str) -> str:
        mapping = {
            "available": "disponible",
            "on_mission": "en_mission",
            "unavailable": "indisponible",
        }
        return mapping.get(v, v)
