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
    nom_complet: str = ""
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
    proof_document_url: Optional[str] = None
    verification_status: str = "pending_upload"
    position_active: bool = False
    position_updated_at: Optional[datetime] = None
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
    def extract_user_info(cls, data):
        user = getattr(data, "user", None) if hasattr(data, "user") else None
        if user is None and isinstance(data, dict):
            user = data.get("user")
        if user:
            nom = user.nom_complet if hasattr(user, "nom_complet") else (user.get("nom_complet") if isinstance(user, dict) else "")
            if isinstance(data, dict):
                data["nom_complet"] = nom
            else:
                data.nom_complet = nom
        return data


class DemandeurInfo(BaseModel):
    id: uuid.UUID
    nom_complet: str
    photo_profil: str | None = None
    role: str


class MecanicienPositionOut(BaseModel):
    """Mécanicien avec position active, visible par les chauffeurs/propriétaires."""
    id: uuid.UUID
    nom_complet: str = ""
    telephone: Optional[str] = None
    photo_url: Optional[str] = None
    specialites: list[str] = []
    disponibilite: str = "disponible"
    localisation_lat: Optional[float] = None
    localisation_lng: Optional[float] = None
    position_active: bool = False
    position_updated_at: Optional[datetime] = None
    distance_km: Optional[float] = None


class MecanicienVerificationUpdate(BaseModel):
    """Décision admin : approuver ou rejeter le justificatif d'un mécanicien."""
    statut: str = Field(..., pattern=r"^(approved|rejected)$")
    motif: Optional[str] = None


# ─── Demande d'assistance ──────────────────────────

class AssistanceCreate(BaseModel):
    type_panne: str = Field(..., pattern=r"^(Mécanique|Pneumatique|Électricité|Carrosserie|Autre)$")
    description: str
    urgence: str = Field(..., pattern=r"^(Faible|Moyenne|Haute|Critique)$")
    localisation_lat: float = Field(..., ge=-90, le=90)
    localisation_lng: float = Field(..., ge=-180, le=180)
    vehicule_description: str = Field(..., max_length=255)


class MecanicienInfo(BaseModel):
    id: uuid.UUID
    nom_complet: str
    photo_profil: str | None = None


class AssistanceUpdateStatut(BaseModel):
    statut: str = Field(..., pattern=r"^(en_attente|pris_en_charge|assignee|en_cours|terminee)$")


class AssistanceOut(BaseModel):
    id: uuid.UUID
    demandeur_id: uuid.UUID
    demandeur_info: Optional[DemandeurInfo] = None
    mecanicien_id: Optional[uuid.UUID] = None
    mecanicien_info: Optional[MecanicienInfo] = None
    type_panne: str
    description: str
    urgence: str
    vehicule_description: str
    statut: str
    localisation_lat: Optional[float] = None
    localisation_lng: Optional[float] = None
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
    def extract_demandeur(cls, data):
        demandeur = getattr(data, "demandeur", None) if hasattr(data, "demandeur") else None
        if demandeur is None and isinstance(data, dict):
            demandeur = data.get("demandeur")
        if demandeur:
            info = DemandeurInfo(
                id=demandeur.id,
                nom_complet=demandeur.nom_complet,
                photo_profil=demandeur.photo_profil,
                role=demandeur.role.value if hasattr(demandeur.role, "value") else demandeur.role,
            )
            if isinstance(data, dict):
                data["demandeur_info"] = info
            else:
                data.demandeur_info = info
        return data

    @model_validator(mode="before")
    @classmethod
    def extract_mecanicien(cls, data):
        mecanicien = getattr(data, "mecanicien", None) if hasattr(data, "mecanicien") else None
        if mecanicien is None and isinstance(data, dict):
            mecanicien = data.get("mecanicien")
        if mecanicien:
            user = getattr(mecanicien, "user", None) if hasattr(mecanicien, "user") else None
            if user:
                info = MecanicienInfo(
                    id=mecanicien.id,
                    nom_complet=user.nom_complet,
                    photo_profil=user.photo_profil,
                )
                if isinstance(data, dict):
                    data["mecanicien_info"] = info
                else:
                    data.mecanicien_info = info
        return data
