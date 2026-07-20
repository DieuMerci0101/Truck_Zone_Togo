from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func  # type: ignore
from sqlalchemy.dialects.postgresql import UUID  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore

from app.models.base import Base
from app.models.enums import StatutDocument, TypeDocument

if TYPE_CHECKING:
    from app.models.user import User


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True
    )
    utilisateur_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type_document: Mapped[TypeDocument] = mapped_column(
        Enum(TypeDocument, name="type_document", create_constraint=True),
        nullable=False,
    )
    fichier_url: Mapped[str] = mapped_column(String(500), nullable=False)
    statut: Mapped[StatutDocument] = mapped_column(
        Enum(StatutDocument, name="statut_document", create_constraint=True),
        nullable=False,
        default=StatutDocument.en_attente,
    )
    commentaire_admin: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    validated_at = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    utilisateur: Mapped["User"] = relationship("User", back_populates="documents")