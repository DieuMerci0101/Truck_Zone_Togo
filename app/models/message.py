from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, Text, func  # type: ignore
from sqlalchemy.dialects.postgresql import UUID  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore

from app.models.base import Base
from app.models.enums import TypeMessage

if TYPE_CHECKING:
    from app.models.conversation import Conversation
    from app.models.user import User


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True
    )
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    expediteur_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    contenu: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[TypeMessage] = mapped_column(
        Enum(TypeMessage, name="type_message", create_constraint=True),
        nullable=False,
        default=TypeMessage.texte,
    )
    media_url: Mapped[str | None] = mapped_column(String(500), nullable=True, default=None)
    lu: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="messages"
    )
    expediteur: Mapped["User"] = relationship("User", back_populates="messages_envoyes")