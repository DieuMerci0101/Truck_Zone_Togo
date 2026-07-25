from __future__ import annotations

from sqlalchemy import Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.enums import EtatCamion, TypeCamion


class Camion(TimestampMixin, Base):
    __tablename__ = "camions"

    proprietaire_id: Mapped[str | None] = mapped_column(
        ForeignKey("profils_proprietaire.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    chauffeur_id: Mapped[str | None] = mapped_column(
        ForeignKey("profils_chauffeur.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    immatriculation: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, nullable=False
    )
    marque: Mapped[str] = mapped_column(String(100), nullable=False)
    modele: Mapped[str] = mapped_column(String(100), nullable=False)
    annee: Mapped[int] = mapped_column(Integer, nullable=False)
    type_camion: Mapped[TypeCamion] = mapped_column(
        Enum(TypeCamion, name="type_camion", create_constraint=True),
        nullable=False,
    )
    capacite_charge: Mapped[float] = mapped_column(Float, nullable=False)
    etat: Mapped[EtatCamion] = mapped_column(
        Enum(EtatCamion, name="etat_camion", create_constraint=True),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_principale_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    is_public: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Relationships (string-based to avoid circular imports)
    proprietaire: Mapped["ProfilProprietaire | None"] = relationship(
        "ProfilProprietaire", back_populates="camions"
    )
    chauffeur: Mapped["ProfilChauffeur | None"] = relationship(
        "ProfilChauffeur", back_populates="camions"
    )
    photos: Mapped[list["CamionPhoto"]] = relationship(
        "CamionPhoto", back_populates="camion", cascade="all, delete-orphan"
    )
    offres: Mapped[list["OffreRecrutement"]] = relationship(
        "OffreRecrutement", back_populates="camion"
    )
