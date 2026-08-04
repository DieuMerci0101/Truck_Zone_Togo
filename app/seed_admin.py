"""
Script idempotent de création / mise à jour du compte administrateur.

Garantit qu'un compte administrateur existe avec :
  - Email    : admin@togotruckconnect.com
  - Mot de passe : Admin@2026
  - Rôle     : admin (rôle privilégié, comparé de façon insensible à la casse
               côté API — 'ADMIN' et 'admin' sont équivalents)
  - is_verified=True, is_active=True

Usage :
    python -m app.seed_admin
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from passlib.hash import bcrypt  # type: ignore
from sqlalchemy import select

from app.database import async_session, engine
from app.models.enums import UserRole
from app.models.user import User

ADMIN_EMAIL = "admin@togotruckconnect.com"
ADMIN_PASSWORD = "Admin@2026"
ADMIN_NAME = "Admin TogoTruck"
ADMIN_PHONE = "+22890123456"


async def seed_admin():
    async with async_session() as db:
        result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
        admin = result.scalar_one_or_none()

        if admin:
            admin.role = UserRole.admin
            admin.is_verified = True
            admin.is_active = True
            admin.password_hash = bcrypt.hash(ADMIN_PASSWORD)
            admin.nom_complet = admin.nom_complet or ADMIN_NAME
            await db.commit()
            print(f"Compte administrateur mis à jour : {ADMIN_EMAIL}")
        else:
            admin = User(
                id=uuid.uuid4(),
                email=ADMIN_EMAIL,
                password_hash=bcrypt.hash(ADMIN_PASSWORD),
                nom_complet=ADMIN_NAME,
                telephone=ADMIN_PHONE,
                role=UserRole.admin,
                is_verified=True,
                is_active=True,
            )
            db.add(admin)
            await db.commit()
            print(f"Compte administrateur créé : {ADMIN_EMAIL}")

        print("Rôle admin garanti, compte actif et vérifié.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_admin())
