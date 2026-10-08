from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, func  # type: ignore
from sqlalchemy.dialects.postgresql import UUID  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore

from app.models.base import Base
from app.models.enums import StatutProposition

if TYPE_CHECKING:
    from app.models.assistance import DemandeAssistance
    from app.models.mecanicien import ProfilMecanicien


class PropositionAssistance(Base):
    """
    Proposition d' prise en charge d'une demande d'assistance par un mécanicien.

    Plusieurs mécaniciens peuvent proposer la MÊME demande ; seul le chauffeur
    (demandeur) décide. Le mécanicien retenu passe à `accepte`, tous les autres
    sont passés automatiquement à `refuse`.

    L'unicité (assistance_id, mecanicien_id) empêche les doubles propositions
    et les doublons en cas de requêtes simultanées.
    """

    __tablename__ = "propositions_assistance"
    __table_args__ = (
        UniqueConstraint(
            "assistance_id",
            "mecanicien_id",
            name="uq_proposition_assistance_demande_mecanicien",
        ),
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True
    )
    assistance_id: Mapped[str] = mapped_column(
        ForeignKey("demandes_assistance.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    mecanicien_id: Mapped[str] = mapped_column(
        ForeignKey("profils_mecanicien.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    # Distance mécanicien ↔ lieu de panne au moment de la proposition.
    distance_km: Mapped[float | None] = mapped_column(nullable=True)
    statut: Mapped[StatutProposition] = mapped_column(
        Enum(
            StatutProposition,
            name="statut_proposition",
            create_constraint=True,
        ),
        nullable=False,
        default=StatutProposition.en_attente,
        server_default="en_attente",
    )
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships (strings pour éviter les imports circulaires)
    assistance: Mapped["DemandeAssistance"] = relationship(
        "DemandeAssistance", back_populates="propositions"
    )
    mecanicien: Mapped["ProfilMecanicien"] = relationship(
        "ProfilMecanicien", back_populates="propositions"
    )
