"""
Service d'audit : enregistre historiquement chaque action critique.

À appeler à chaque mutation importante (POST / PUT / DELETE) avec la session
de base de données courante. L'enregistrement est ajouté à la même
transaction que l'action elle-même (flush) — il est donc committé ou annulé
avec elle, ce qui garantit la cohérence.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def log_action(
    db: AsyncSession,
    user_id: str | None,
    action: str,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Ajoute une entrée d'audit à la transaction courante."""
    db.add(
        AuditLog(
            id=uuid.uuid4(),
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=str(target_id) if target_id is not None else None,
            details=details,
        )
    )
    await db.flush()
