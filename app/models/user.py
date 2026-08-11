import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, Enum, ForeignKey, String, Text  # type: ignore
from sqlalchemy.dialects.postgresql import UUID  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore

from app.models.base import Base, TimestampMixin
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.assistance import DemandeAssistance
    from app.models.chauffeur import ProfilChauffeur
    from app.models.conversation import ConversationParticipant
    from app.models.country import Country
    from app.models.document import Document
    from app.models.incident import Incident, IncidentCommentaire
    from app.models.mecanicien import ProfilMecanicien
    from app.models.message import Message
    from app.models.notification import Notification
    from app.models.candidature import Candidature
    from app.models.otp import OTPReset
    from app.models.photo_profil import PhotoProfil
    from app.models.proprietaire import ProfilProprietaire


class User(TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nom_complet: Mapped[str] = mapped_column(String(255), nullable=False)
    telephone: Mapped[str] = mapped_column(String(20), nullable=False)
    # Pays d'origine de l'utilisateur (table `countries`).
    country_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("countries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", create_constraint=True),
        nullable=False,
    )
    photo_profil: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    # Version incrémentée à chaque changement de photo de profil : sert de
    # cache-buster frontend (src=".../photo?v=<photo_profil_version>").
    photo_profil_version: Mapped[int] = mapped_column(
        nullable=False, default=0, server_default="0"
    )
    date_naissance: Mapped[str | None] = mapped_column(String(10), nullable=True, default=None)
    lieu_naissance: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    adresse: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Vérification du compte (tous rôles) :
    # pending_upload | pending_approval | approved | rejected
    verification_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending_upload",
        server_default="pending_upload",
    )
    # Motif enregistré lors d'un rejet par l'administrateur
    verification_reject_motif: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )

    # Relationships
    country: Mapped["Country | None"] = relationship(
        "Country", back_populates="users"
    )
    profil_chauffeur: Mapped["ProfilChauffeur | None"] = relationship(
        "ProfilChauffeur", back_populates="user", uselist=False
    )
    profil_proprietaire: Mapped["ProfilProprietaire | None"] = relationship(
        "ProfilProprietaire", back_populates="user", uselist=False
    )
    profil_mecanicien: Mapped["ProfilMecanicien | None"] = relationship(
        "ProfilMecanicien", back_populates="user", uselist=False
    )
    documents: Mapped[list["Document"]] = relationship(
        "Document", back_populates="utilisateur"
    )
    otp_resets: Mapped[list["OTPReset"]] = relationship(
        "OTPReset", back_populates="user"
    )
    messages_envoyes: Mapped[list["Message"]] = relationship(
        "Message", back_populates="expediteur"
    )
    conversations: Mapped[list["ConversationParticipant"]] = relationship(
        "ConversationParticipant", back_populates="user"
    )
    incidents_declares: Mapped[list["Incident"]] = relationship(
        "Incident", back_populates="declarant"
    )
    incident_commentaires: Mapped[list["IncidentCommentaire"]] = relationship(
        "IncidentCommentaire", back_populates="auteur"
    )
    demandes_assistance: Mapped[list["DemandeAssistance"]] = relationship(
        "DemandeAssistance", back_populates="demandeur"
    )
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="destinataire"
    )
    candidatures: Mapped[list["Candidature"]] = relationship(
        "Candidature", back_populates="chauffeur"
    )
    photos_profil: Mapped[list["PhotoProfil"]] = relationship(
        "PhotoProfil", back_populates="user"
    )