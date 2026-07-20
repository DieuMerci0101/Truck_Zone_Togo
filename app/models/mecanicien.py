from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String, Text  # type: ignore
from sqlalchemy.dialects.postgresql import ARRAY  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore

from app.models.base import Base, TimestampMixin
from app.models.enums import DisponibiliteMecanicien, TarificationMecanicien

if TYPE_CHECKING:
    from app.models.assistance import DemandeAssistance
    from app.models.user import User

try:
    from geoalchemy2 import Geometry  # type: ignore

    HAS_GEO = True
except ImportError:
    HAS_GEO = False


class ProfilMecanicien(TimestampMixin, Base):
    __tablename__ = "profils_mecanicien"

    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    specialites: Mapped[list[str]] = mapped_column(ARRAY(String), nullable=False)
    annees_experience: Mapped[int] = mapped_column(Integer, nullable=False)
    certifications: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True
    )
    tarification: Mapped[TarificationMecanicien] = mapped_column(
        Enum(
            TarificationMecanicien,
            name="tarification_mecanicien",
            create_constraint=True,
        ),
        nullable=False,
    )
    disponibilite: Mapped[DisponibiliteMecanicien] = mapped_column(
        Enum(
            DisponibiliteMecanicien,
            name="disponibilite_mecanicien",
            create_constraint=True,
        ),
        nullable=False,
        default=DisponibiliteMecanicien.disponible,
    )

    if HAS_GEO:
        localisation = mapped_column(
            Geometry(geometry_type="POINT", srid=4326), nullable=False
        )
    else:
        localisation = mapped_column(String(100), nullable=False)

    rayon_intervention: Mapped[int] = mapped_column(Integer, nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships (référencées en string pour éviter les imports circulaires)
    user: Mapped["User"] = relationship("User", back_populates="profil_mecanicien")
    demandes_recues: Mapped[list["DemandeAssistance"]] = relationship(
        "DemandeAssistance", back_populates="mecanicien"
    )