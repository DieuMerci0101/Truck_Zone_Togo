from typing import TYPE_CHECKING
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func  # type: ignore
from sqlalchemy.dialects.postgresql import UUID  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore

from app.models.base import Base
from app.models.enums import StatutAssistance, TypePanne, Urgence

if TYPE_CHECKING:
    from app.models.mecanicien import ProfilMecanicien
    from app.models.user import User

class DemandeAssistance(Base):
    __tablename__ = "demandes_assistance"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True
    )
    demandeur_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mecanicien_id: Mapped[str | None] = mapped_column(
        ForeignKey("profils_mecanicien.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    type_panne: Mapped[TypePanne] = mapped_column(
        Enum(TypePanne, name="type_panne", create_constraint=True),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    urgence: Mapped[Urgence] = mapped_column(
        Enum(Urgence, name="urgence", create_constraint=True),
        nullable=False,
    )
    localisation = mapped_column(String(100), nullable=False, default="POINT(0 0)")

    vehicule_description: Mapped[str] = mapped_column(String(255), nullable=False)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    statut: Mapped[StatutAssistance] = mapped_column(
        Enum(StatutAssistance, name="statut_assistance", create_constraint=True),
        nullable=False,
        default=StatutAssistance.en_attente,
    )
    # « Premier arrivé » : horodatage du moment où un mécanicien a pris la
    # demande en charge (verrouillage atomique côté API).
    pris_en_charge_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
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

    # Relationships (référencées en string pour éviter les imports circulaires)
    demandeur: Mapped["User"] = relationship(
        "User", back_populates="demandes_assistance"
    )
    mecanicien: Mapped["ProfilMecanicien | None"] = relationship(
        "ProfilMecanicien", back_populates="demandes_recues"
    )