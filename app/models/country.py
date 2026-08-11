import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, func  # type: ignore
from sqlalchemy.dialects.postgresql import UUID  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column, relationship  # type: ignore

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class Country(Base):
    """Pays et indicatifs téléphoniques internationaux (format E.164)."""

    __tablename__ = "countries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(2), unique=True, index=True, nullable=False)
    phone_code: Mapped[str] = mapped_column(String(10), nullable=False)
    flag_emoji: Mapped[str | None] = mapped_column(String(16), nullable=True, default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Utilisateurs rattachés à ce pays.
    users: Mapped[list["User"]] = relationship("User", back_populates="country")
