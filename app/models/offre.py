from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import StatutOffre, TypeContrat


class OffreRecrutement(TimestampMixin, Base):
    __tablename__ = "offres_recrutement"

    proprietaire_id: Mapped[str] = mapped_column(
        ForeignKey("profils_proprietaire.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    titre: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    type_contrat: Mapped[TypeContrat] = mapped_column(
        Enum(TypeContrat, name="type_contrat", create_constraint=True),
        nullable=False,
    )
    salaire_propose: Mapped[float] = mapped_column(Float, nullable=False)
    zone_travail: Mapped[str] = mapped_column(String(255), nullable=False)
    date_debut: Mapped[date] = mapped_column(Date, nullable=False)
    camion_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("camions.id", ondelete="SET NULL"), nullable=True
    )
    statut: Mapped[StatutOffre] = mapped_column(
        Enum(StatutOffre, name="statut_offre", create_constraint=True),
        nullable=False,
        default=StatutOffre.active,
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships (string-based to avoid circular imports)
    proprietaire: Mapped["ProfilProprietaire"] = relationship(
        "ProfilProprietaire", back_populates="offres"
    )
    camion: Mapped[Optional["Camion"]] = relationship(
        "Camion", back_populates="offres"
    )
