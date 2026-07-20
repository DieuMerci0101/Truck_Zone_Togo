"""
Script de création du premier compte administrateur.

Ce script crée un compte admin dans la base de données avec un mot de passe
haché par bcrypt. Il est conçu pour être exécuté une seule fois lors de
l'initialisation du système.

─────────────────────────────────────────────────────────────
EXPLICATION : COMMENT FONCTIONNE LE HACHAGE DE MOT DE PASSE
─────────────────────────────────────────────────────────────

Le mot de passe n'est JAMAIS stocké en clair dans la base de données.
On utilise l'algorithme bcrypt qui :
1. Génère un "salt" (une chaîne aléatoire unique pour chaque utilisateur)
2. Combine le salt + le mot de passe
3. Applique l'algorithme de hachage bcrypt (12 rounds par défaut)
4. Le résultat est une chaîne comme : $2b$12$LJ3m4ys3Gz3Gz3Gz3Gz3GuYqZqZqZqZqZqZqZqZqZqZqZqZqZqZ

Avantages de bcrypt :
- Même si deux utilisateurs ont le même mot de passe, leurs hachages seront différents (grâce au salt)
- La vérification se fait avec bcrypt.verify(mot_de_passe_clair, hash) → True/False
- Il est extrêmement lent à bruter (12 rounds = ~250ms par tentative)

Dans ce script, on utilise :
  from passlib.hash import bcrypt
  hashed = bcrypt.hash("Admin@123")  # Hachage du mot de passe
  bcrypt.verify("Admin@123", hashed)  # Vérification → True

─────────────────────────────────────────────────────────────
EXPLICATION : LA COLONNE 'role' DANS LA TABLE 'users'
─────────────────────────────────────────────────────────────

La colonne 'role' utilise un type ENUM PostgreSQL nommé 'user_role'.
Les valeurs autorisées sont définies dans app/models/enums.py :

  class UserRole(str, Enum):
      chauffeur = "chauffeur"
      proprietaire = "proprietaire"
      mecanicien = "mecanicien"
      admin = "admin"

Au niveau SQL, cela crée :
  CREATE TYPE user_role AS ENUM ('chauffeur', 'proprietaire', 'mecanicien', 'admin');

La colonne dans la table users :
  role user_role NOT NULL

Avantages de l'ENUM :
- La base de données rejette toute valeur non autorisée (sécurité)
- Requêtes plus rapides qu'un simple VARCHAR
- Documentation intégrée du schéma

Pour vérifier/créer le type ENUM manuellement :
  SELECT typname, enumlabel FROM pg_enum WHERE typname = 'user_role';

─────────────────────────────────────────────────────────────
EXPLICATION : LE SYSTÈME JWT (JSON WEB TOKEN)
─────────────────────────────────────────────────────────────

Le JWT est un standard pour l'authentification. Sa structure :
  HEADER.PAYLOAD.SIGNATURE

1. HEADER : {"alg": "HS256", "typ": "JWT"}
2. PAYLOAD : {"sub": "user_id", "role": "admin", "exp": 1234567890}
3. SIGNATURE : HMAC-SHA256(header + payload, secret_key)

Le token est signé avec une clé secrète (JWT_SECRET_KEY dans .env).
Côté backend, on vérifie :
- La signature (pour détecter les falsifications)
- L'expiration (pour détecter les tokens périmés)
- Le rôle (pour contrôler l'accès)

─────────────────────────────────────────────────────────────
"""

import asyncio
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import async_session, engine
from app.models.user import User
from app.models.enums import UserRole
from passlib.hash import bcrypt  # type: ignore


# ──────────────────────────────────────────────────────────
# Configuration du premier administrateur
# ──────────────────────────────────────────────────────────
ADMIN_EMAIL = "admin@togotruckconnect.com"
ADMIN_PASSWORD = "Admin@123"  # À changer en production !
ADMIN_NOM = "Admin TogoTruck"
ADMIN_TELEPHONE = "+22890123456"


async def create_admin():
    """
    Crée le premier compte administrateur dans la base de données.

    Étapes :
    1. Vérifier si un admin existe déjà (éviter les doublons)
    2. Hacher le mot de passe avec bcrypt
    3. Insérer l'utilisateur avec le rôle 'admin'
    4. Valider la création
    """
    print("🔧 Création du compte administrateur...")
    print(f"   Email: {ADMIN_EMAIL}")
    print(f"   Rôle: admin")
    print()

    async with async_session() as db:
        # Vérifier si un admin existe déjà
        from sqlalchemy import select, func

        result = await db.execute(
            select(func.count()).select_from(User).where(User.role == UserRole.admin)
        )
        admin_count = result.scalar()

        if admin_count > 0:
            print("⚠️  Un compte administrateur existe déjà dans la base.")
            print("   Pour créer un nouvel admin, modifiez les constantes en haut du script.")
            print()
            # Afficher les admins existants
            admins = await db.execute(
                select(User).where(User.role == UserRole.admin)
            )
            for admin in admins.scalars():
                print(f"   - {admin.email} ({admin.nom_complet})")
            await engine.dispose()
            return

        # Hacher le mot de passe avec bcrypt
        # bcrypt.hash() génère un salt aléatoire + hache le mot de passe
        # Résultat : une chaîne de 60 caractères comme "$2b$12$LJ3m4ys3Gz..."
        password_hash = bcrypt.hash(ADMIN_PASSWORD)

        # Créer l'utilisateur admin
        admin = User(
            id=uuid.uuid4(),
            email=ADMIN_EMAIL,
            password_hash=password_hash,
            nom_complet=ADMIN_NOM,
            telephone=ADMIN_TELEPHONE,
            role=UserRole.admin,  # ENUM: 'admin' dans PostgreSQL
            is_verified=True,     # Admin toujours vérifié
            is_active=True,       # Admin toujours actif
        )
        db.add(admin)
        await db.commit()
        await db.refresh(admin)

        print("✅ Compte administrateur créé avec succès !")
        print()
        print("📋 Détails de connexion :")
        print(f"   Email:    {ADMIN_EMAIL}")
        print(f"   Mot de passe: {ADMIN_PASSWORD}")
        print(f"   UUID:     {admin.id}")
        print()
        print("🔑 Comment le mot de passe est stocké :")
        print(f"   Clair:    {ADMIN_PASSWORD}")
        print(f"   Haché:    {admin.password_hash[:60]}...")
        print()
        print("🔐 Vérification bcrypt :")
        print(f"   bcrypt.verify('{ADMIN_PASSWORD}', hash) = {bcrypt.verify(ADMIN_PASSWORD, admin.password_hash)}")
        print(f"   bcrypt.verify('mauvais_mdp', hash)     = {bcrypt.verify('mauvais_mdp', admin.password_hash)}")
        print()
        print("🌐 Pour se connecter :")
        print("   1. Aller sur http://localhost:3000/admin/login")
        print(f"   2. Email: {ADMIN_EMAIL}")
        print(f"   3. Mot de passe: {ADMIN_PASSWORD}")
        print()
        print("⚠️  IMPORTANT : Changez le mot de passe en production !")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(create_admin())
