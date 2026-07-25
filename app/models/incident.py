from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func  # type: ignore
from sqlalchemy.dialects.postgresql import ARRAY, UUID  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore

from app.models.base import Base
from app.models.enums import GraviteIncident, StatutIncident, TypeIncident

if TYPE_CHECKING:
    from app.models.user import User

class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True
    )
    declarant_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type_incident: Mapped[TypeIncident] = mapped_column(
        Enum(TypeIncident, name="type_incident", create_constraint=True),
        nullable=False,
    )
    date_incident = mapped_column(DateTime(timezone=True), nullable=False)
    localisation = mapped_column(String(100), nullable=False, default="POINT(0 0)")

    description: Mapped[str] = mapped_column(Text, nullable=False)
    gravite: Mapped[GraviteIncident] = mapped_column(
        Enum(GraviteIncident, name="gravite_incident", create_constraint=True),
        nullable=False,
    )
    vehicules_impliques: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    victimes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    nombre_victimes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    statut: Mapped[StatutIncident] = mapped_column(
        Enum(StatutIncident, name="statut_incident", create_constraint=True),
        nullable=False,
        default=StatutIncident.declare,
    )
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    temoin_contact: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    declarant: Mapped["User"] = relationship("User", back_populates="incidents_declares")
    commentaires: Mapped[list["IncidentCommentaire"]] = relationship(
        "IncidentCommentaire", back_populates="incident"
    )


class IncidentCommentaire(Base):
    __tablename__ = "incident_commentaires"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True
    )
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    auteur_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contenu: Mapped[str] = mapped_column(Text, nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    incident: Mapped["Incident"] = relationship(
        "Incident", back_populates="commentaires"
    )
    auteur: Mapped["User"] = relationship(
        "User", back_populates="incident_commentaires"
    )