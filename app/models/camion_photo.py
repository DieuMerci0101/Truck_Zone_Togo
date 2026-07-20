from __future__ import annotations

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class CamionPhoto(Base):
    __tablename__ = "camion_photos"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), primary_key=True, index=True
    )
    camion_id: Mapped[str] = mapped_column(
        ForeignKey("camions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    photo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    est_principale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships (string-based to avoid circular imports)
    camion: Mapped["Camion"] = relationship("Camion", back_populates="photos")
