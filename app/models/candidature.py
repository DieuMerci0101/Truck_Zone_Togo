from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.offre import OffreRecrutement
    from app.models.user import User


class Candidature(Base):
    __tablename__ = "candidatures"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, index=True)
    offre_id: Mapped[str] = mapped_column(
        ForeignKey("offres_recrutement.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    chauffeur_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    statut: Mapped[str] = mapped_column(
        String(20), nullable=False, default="en_attente"
    )
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    offre: Mapped["OffreRecrutement"] = relationship("OffreRecrutement", back_populates="candidatures")
    chauffeur: Mapped["User"] = relationship("User", back_populates="candidatures")
