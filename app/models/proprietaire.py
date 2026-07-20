from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore

from app.models.base import Base, TimestampMixin
from app.models.enums import TypeActivite

if TYPE_CHECKING:
    from app.models.camion import Camion
    from app.models.offre import OffreRecrutement
    from app.models.user import User

try:
    from geoalchemy2 import Geometry  # type: ignore

    HAS_GEO = True
except ImportError:
    HAS_GEO = False


class ProfilProprietaire(TimestampMixin, Base):
    __tablename__ = "profils_proprietaire"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    nom_entreprise: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type_activite: Mapped[TypeActivite] = mapped_column(
        Enum(TypeActivite, name="type_activite", create_constraint=True),
        nullable=False,
    )
    adresse: Mapped[str] = mapped_column(String(500), nullable=False)

    if HAS_GEO:
        localisation = mapped_column(
            Geometry(geometry_type="POINT", srid=4326), nullable=False
        )
    else:
        localisation = mapped_column(String(100), nullable=False)

    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="profil_proprietaire")
    camions: Mapped[list["Camion"]] = relationship(
        "Camion", back_populates="proprietaire"
    )
    offres: Mapped[list["OffreRecrutement"]] = relationship(
        "OffreRecrutement", back_populates="proprietaire"
    )