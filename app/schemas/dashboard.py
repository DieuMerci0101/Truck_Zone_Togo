"""Schémas du tableau de bord (vue client dès la connexion + vue admin)."""

from datetime import datetime
from pydantic import BaseModel, Field


class CandidatureLeger(BaseModel):
    """Résumé d'une candidature — sans données sensibles inutiles."""

    id: str
    offre_titre: str | None = None
    statut: str
    chauffeur_nom: str | None = None
    updated_at: datetime | None = None


class DashboardOverview(BaseModel):
    """
    Vue d'ensemble pour l'utilisateur connecté.

    Un seul appel pour afficher : statut du compte, notifications non lues,
    messages non lus, nouvelles demandes, réponses aux candidatures et
    interventions en cours. Les champs inutiles pour un rôle sont `None`.
    Structure stable pour compatibilité avec une application mobile native.
    """

    role: str
    date: datetime
    statut_verification: str
    is_verified: bool
    notifications_non_lues: int = 0
    messages_non_lus: int = 0

    # Statut métier
    disponibilite: str | None = None
    position_active: bool | None = None

    # Candidatures — côté chauffeur (mes réponses)
    candidatures_en_attente: int = 0
    candidatures_acceptees: int = 0
    candidatures_refusees: int = 0
    dernieres_reponses_candidatures: list[CandidatureLeger] = Field(default_factory=list)

    # Candidatures — côté propriétaire (recues)
    candidatures_recues: int = 0
    candidatures_recues_en_attente: int = 0
    dernieres_candidatures_recues: list[CandidatureLeger] = Field(default_factory=list)

    # Offres / camions — côté propriétaire
    offres_actives: int = 0
    camions_publies: int = 0

    # Assistance mécanique
    interventions_actives: int = 0
    interventions_terminees: int = 0
    demandes_disponibles: int = 0

    # Vue administrateur (agrégats uniquement)
    stats: dict | None = None
