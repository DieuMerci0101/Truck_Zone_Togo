import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.models.user import User
from app.models.enums import UserRole, TypeNotification


async def create_notification(
    db: AsyncSession,
    destinataire_id: uuid.UUID,
    titre: str,
    contenu: str,
    type_notif: str = "systeme",
    lien: str | None = None,
) -> Notification:
    notification = Notification(
        id=uuid.uuid4(),
        destinataire_id=destinataire_id,
        titre=titre,
        contenu=contenu,
        type=type_notif,
        lien=lien,
    )
    db.add(notification)
    return notification


async def notify_all_admins(
    db: AsyncSession,
    titre: str,
    contenu: str,
    type_notif: str = "admin",
    lien: str | None = None,
) -> list[Notification]:
    result = await db.execute(
        select(User).where(User.role == UserRole.admin, User.is_active == True)
    )
    admins = result.scalars().all()
    notifications = []
    for admin in admins:
        n = await create_notification(
            db,
            destinataire_id=admin.id,
            titre=titre,
            contenu=contenu,
            type_notif=type_notif,
            lien=lien,
        )
        notifications.append(n)
    return notifications


async def notify_user(
    db: AsyncSession,
    user_id: uuid.UUID,
    titre: str,
    contenu: str,
    type_notif: str = "systeme",
    lien: str | None = None,
) -> Notification:
    return await create_notification(db, user_id, titre, contenu, type_notif, lien)
