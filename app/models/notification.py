import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore

from app.models.base import Base, TimestampMixin
from app.models.enums import TypeNotification


class Notification(TimestampMixin, Base):
    __tablename__ = "notifications"

    destinataire_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    titre: Mapped[str] = mapped_column(String(255), nullable=False)
    contenu: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[TypeNotification] = mapped_column(
        Enum(TypeNotification, name="type_notification", create_constraint=True),
        nullable=False,
        default=TypeNotification.systeme,
    )
    lu: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lien: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    destinataire: Mapped["User"] = relationship("User", back_populates="notifications")  # noqa: F821
