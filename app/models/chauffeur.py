from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Text  # type: ignore
from sqlalchemy.dialects.postgresql import ARRAY  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore

from app.models.base import Base, TimestampMixin
from app.models.enums import (
    CategoriePermis,
    DisponibiliteChauffeur,
    TypeTransport,
)

if TYPE_CHECKING:
    from app.models.user import User


class ProfilChauffeur(TimestampMixin, Base):
    __tablename__ = "profils_chauffeur"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    numero_permis: Mapped[str] = mapped_column(String(50), nullable=False)
    categorie_permis: Mapped[CategoriePermis] = mapped_column(
        Enum(CategoriePermis, name="categorie_permis", create_constraint=True),
        nullable=False,
    )
    annees_experience: Mapped[int] = mapped_column(Integer, nullable=False)
    types_transport: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False
    )
    zones_circulation: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False
    )
    disponibilite: Mapped[DisponibiliteChauffeur] = mapped_column(
        Enum(
            DisponibiliteChauffeur,
            name="disponibilite_chauffeur",
            create_constraint=True,
        ),
        nullable=False,
        default=DisponibiliteChauffeur.disponible,
    )
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profil_chauffeur")