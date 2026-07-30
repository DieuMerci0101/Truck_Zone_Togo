import uuid
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import inspect as sa_inspect


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


# ─── Profil Propriétaire ───────────────────────────

class ProfilProprietaireCreate(BaseModel):
    nom_entreprise: Optional[str] = None
    type_activite: str = Field(..., pattern=r"^(transport|logistique|btp|agriculture|minier|autre)$")
    adresse: str = Field(..., max_length=500)
    localisation_lat: float = Field(..., ge=-90, le=90)
    localisation_lng: float = Field(..., ge=-180, le=180)
    bio: Optional[str] = None


class ProfilProprietaireUpdate(BaseModel):
    nom_entreprise: Optional[str] = None
    type_activite: Optional[str] = None
    adresse: Optional[str] = None
    localisation_lat: Optional[float] = Field(None, ge=-90, le=90)
    localisation_lng: Optional[float] = Field(None, ge=-180, le=180)
    bio: Optional[str] = None
    photo_url: Optional[str] = None


class ProfilProprietaireOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    nom_entreprise: Optional[str] = None
    type_activite: str
    adresse: str
    localisation_lat: Optional[float] = None
    localisation_lng: Optional[float] = None
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


# ─── Camion ────────────────────────────────────────

class CamionPhotoOut(BaseModel):
    id: uuid.UUID
    camion_id: uuid.UUID
    photo_url: str
    est_principale: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class CamionCreate(BaseModel):
    immatriculation: str = Field(..., max_length=50)
    marque: str = Field(..., max_length=100)
    modele: str = Field(..., max_length=100)
    annee: int = Field(..., ge=1900, le=2100)
    type_camion: str = Field(..., pattern=r"^(porteur|semi_remorque|benne|citerne|frigorifique|bache|plateau|benne_soulevable|autre)$")
    capacite_charge: float = Field(..., gt=0)
    etat: str = Field(..., pattern=r"^(bon_etat|excellent|bon|use|en_reparation)$")
    description: Optional[str] = None
    is_public: bool = False
    expires_at: Optional[datetime] = None
    nb_essieux: Optional[int] = Field(None, ge=2, le=12)
    carburant: Optional[str] = Field(None, pattern=r"^(diesel|essence|gaz|electrique|hybride)$")
    boite_vitesse: Optional[str] = Field(None, pattern=r"^(manuelle|automatique)$")
    kilometrage: Optional[float] = Field(None, ge=0)
    localisation: Optional[str] = Field(None, max_length=255)


class CamionUpdate(BaseModel):
    immatriculation: Optional[str] = None
    marque: Optional[str] = None
    modele: Optional[str] = None
    annee: Optional[int] = Field(None, ge=1900, le=2100)
    type_camion: Optional[str] = None
    capacite_charge: Optional[float] = Field(None, gt=0)
    etat: Optional[str] = None
    description: Optional[str] = None
    is_public: Optional[bool] = None
    expires_at: Optional[datetime] = None
    nb_essieux: Optional[int] = Field(None, ge=2, le=12)
    carburant: Optional[str] = Field(None, pattern=r"^(diesel|essence|gaz|electrique|hybride)$")
    boite_vitesse: Optional[str] = Field(None, pattern=r"^(manuelle|automatique)$")
    kilometrage: Optional[float] = Field(None, ge=0)
    localisation: Optional[str] = Field(None, max_length=255)


class ProprietaireInfoOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    nom_complet: str
    email: str
    telephone: str
    photo_profil: Optional[str] = None

    model_config = {"from_attributes": True}


class CamionOut(BaseModel):
    id: uuid.UUID
    proprietaire_id: Optional[uuid.UUID] = None
    chauffeur_id: Optional[uuid.UUID] = None
    immatriculation: str
    marque: str
    modele: str
    annee: int
    type_camion: str
    capacite_charge: float
    etat: str
    description: Optional[str] = None
    photo_principale_url: Optional[str] = None
    is_public: bool = False
    expires_at: Optional[datetime] = None
    nb_essieux: Optional[int] = None
    carburant: Optional[str] = None
    boite_vitesse: Optional[str] = None
    kilometrage: Optional[float] = None
    localisation: Optional[str] = None
    photos: list[CamionPhotoOut] = []
    proprietaire_info: Optional[ProprietaireInfoOut] = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def extract_proprietaire_info(cls, data):
        prop = None
        if isinstance(data, dict):
            prop = data.get("proprietaire")
        else:
            insp = sa_inspect(data)
            if "proprietaire" not in insp.unloaded:
                prop = data.proprietaire
        if prop is not None:
            user = getattr(prop, "user", None) if not isinstance(prop, dict) else prop.get("user")
            if user is not None:
                info = {
                    "id": getattr(prop, "id", None) if not isinstance(prop, dict) else prop.get("id"),
                    "user_id": getattr(user, "id", None) if not isinstance(user, dict) else user.get("id"),
                    "nom_complet": getattr(user, "nom_complet", None) if not isinstance(user, dict) else user.get("nom_complet"),
                    "email": getattr(user, "email", None) if not isinstance(user, dict) else user.get("email"),
                    "telephone": getattr(user, "telephone", None) if not isinstance(user, dict) else user.get("telephone"),
                    "photo_profil": getattr(user, "photo_profil", None) if not isinstance(user, dict) else user.get("photo_profil"),
                }
                if isinstance(data, dict):
                    data["proprietaire_info"] = info
                else:
                    setattr(data, "proprietaire_info", info)
        return data


class CamionProlonger(BaseModel):
    expires_at: datetime = Field(...)


# ─── Offre de recrutement ──────────────────────────

class OffreCreate(BaseModel):
    titre: str = Field(..., max_length=255)
    description: str
    type_contrat: str = Field(..., pattern=r"^(CDD|CDI|Mission ponctuelle)$")
    salaire_propose: float = Field(..., gt=0)
    zone_travail: str = Field(..., max_length=255)
    date_debut: str
    camion_id: Optional[uuid.UUID] = None


class OffreUpdate(BaseModel):
    titre: Optional[str] = None
    description: Optional[str] = None
    type_contrat: Optional[str] = None
    salaire_propose: Optional[float] = Field(None, gt=0)
    zone_travail: Optional[str] = None
    date_debut: Optional[str] = None
    camion_id: Optional[uuid.UUID] = None


class OffreOut(BaseModel):
    id: uuid.UUID
    proprietaire_id: uuid.UUID
    titre: str
    description: str
    type_contrat: str
    salaire_propose: float
    zone_travail: str
    date_debut: str
    camion_id: Optional[uuid.UUID] = None
    statut: str
    created_at: datetime
    is_editable: bool = False

    model_config = {"from_attributes": True}
