import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column  # type: ignore

from app.models.base import Base


class NotificationPreference(Base):
    """
    Préférences de notification de l'utilisateur (un seul enregistrement par
    utilisateur) : quels canaux activer pour éviter le spam.
        - email : email de notification (via Brevo API)
        - push  : Web Push (PWA)
        - sms   : SMS de secours (urgences uniquement)
        - in_app : notification dans l'application (toujours enregistrée en base)
    """

    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    email: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    push: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sms: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    in_app: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Horodatage de la dernière modification.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class PushSubscription(Base):
    """
    Abonnement Web Push d'un navigateur/appareil (PWA).
    `endpoint` est unique : le même appareil ne peut pas être abonné deux fois.
    """

    __tablename__ = "push_subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    endpoint: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    p256dh: Mapped[str] = mapped_column(String(512), nullable=False)
    auth: Mapped[str] = mapped_column(String(256), nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
