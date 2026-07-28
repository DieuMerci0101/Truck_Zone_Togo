from typing import TYPE_CHECKING

import uuid
from sqlalchemy import DateTime, Enum, ForeignKey, String, Text, func  # type: ignore
from sqlalchemy.dialects.postgresql import UUID  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore

from app.models.base import Base
from app.models.enums import TypeConversation

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.user import User


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True, default=uuid.uuid4
    )
    type: Mapped[TypeConversation] = mapped_column(
        Enum(TypeConversation, name="type_conversation", create_constraint=True),
        nullable=False,
        default=TypeConversation.directe,
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

    # Relationships
    participants: Mapped[list["ConversationParticipant"]] = relationship(
        "ConversationParticipant", back_populates="conversation"
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="conversation"
    )


class ConversationParticipant(Base):
    __tablename__ = "conversation_participants"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    joined_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    conversation: Mapped["Conversation"] = relationship(
        "Conversation", back_populates="participants"
    )
    user: Mapped["User"] = relationship("User", back_populates="conversations")