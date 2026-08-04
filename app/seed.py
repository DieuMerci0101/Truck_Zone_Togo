"""
Script pour remplir la base avec les données de démonstration.
Usage: python -m app.seed
"""
import asyncio
import sys
import os
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import async_session, engine
from app.models import (
    User,
    ProfilChauffeur,
    ProfilProprietaire,
    ProfilMecanicien,
    Camion,
    CamionPhoto,
    UserRole,
    CategoriePermis,
    DisponibiliteChauffeur,
    TypeActivite,
    DisponibiliteMecanicien,
    TarificationMecanicien,
    EtatCamion,
    TypeCamion,
)
from passlib.hash import bcrypt # type: ignore

ADMIN_EMAIL = "admin@togotruckconnect.com"
ADMIN_PASSWORD = "Admin@2026"


async def ensure_admin(db):
    """Crée le compte administrateur s'il n'existe pas (idempotent)."""
    from sqlalchemy import select

    result = await db.execute(select(User).where(User.email == ADMIN_EMAIL))
    existing = result.scalar_one_or_none()
    if existing:
        if existing.role != UserRole.admin:
            existing.role = UserRole.admin
            existing.is_verified = True
            existing.is_active = True
            await db.flush()
            print(f"✅ Rôle du compte existant corrigé en 'admin' : {ADMIN_EMAIL}")
        else:
            print(f"ℹ️  Compte admin déjà présent : {ADMIN_EMAIL}")
        return existing

    admin = User(
        id=uuid.uuid4(),
        email=ADMIN_EMAIL,
        password_hash=bcrypt.hash(ADMIN_PASSWORD),
        nom_complet="Admin TogoTruck",
        telephone="+22890123456",
        role=UserRole.admin,
        is_verified=True,
        is_active=True,
    )
    db.add(admin)
    await db.flush()
    print(f"✅ Compte admin créé : {ADMIN_EMAIL}")
    return admin


async def seed():
    print("🌱 Insertion des données de démonstration...")

    async with async_session() as db:
        await ensure_admin(db)

        # ── Chauffeur ──
        async def user_exists(email: str) -> bool:
            from sqlalchemy import select

            r = await db.execute(select(User.id).where(User.email == email))
            return r.scalar_one_or_none() is not None

        chauffeur_email = "kofi.chauffeur@email.com"
        async def camion_exists(immatriculation: str) -> bool:
            from sqlalchemy import select

            r = await db.execute(select(Camion.id).where(Camion.immatriculation == immatriculation))
            return r.scalar_one_or_none() is not None

        if await user_exists(chauffeur_email):
            print(f"ℹ️  Chauffeur déjà présent : {chauffeur_email}")
        else:
            chauffeur_user = User(
                id=uuid.uuid4(),
                email=chauffeur_email,
                password_hash=bcrypt.hash("Chauffeur@123"),
                nom_complet="Kofi Amedee",
                telephone="+22891234567",
                role=UserRole.chauffeur,
                is_verified=True,
                is_active=True,
            )
            db.add(chauffeur_user)

            profil_chauffeur = ProfilChauffeur(
                id=uuid.uuid4(),
                user_id=chauffeur_user.id,
                numero_permis="TG-2020-12345",
                categorie_permis=CategoriePermis.C,
                annees_experience=5,
                types_transport=["marchandises", "conteneurs"],
                zones_circulation=["Lomé", "Kara", "Sokodé"],
                disponibilite=DisponibiliteChauffeur.disponible,
                bio="Chauffeur expérimenté, ponctuel et rigoureux.",
            )
            db.add(profil_chauffeur)

        # ── Propriétaire ──
        proprio_email = "abi.proprietaire@email.com"
        profil_proprio = None
        if await user_exists(proprio_email):
            print(f"ℹ️  Propriétaire déjà présent : {proprio_email}")
        else:
            proprio_user = User(
                id=uuid.uuid4(),
                email=proprio_email,
                password_hash=bcrypt.hash("Proprio@123"),
                nom_complet="Abi Console",
                telephone="+22892345678",
                role=UserRole.proprietaire,
                is_verified=True,
                is_active=True,
            )
            db.add(proprio_user)

            profil_proprio = ProfilProprietaire(
                id=uuid.uuid4(),
                user_id=proprio_user.id,
                nom_entreprise="Console Transport SARL",
                type_activite=TypeActivite.transport,
                adresse="Boulevard du 13 Janvier, Lomé",
                localisation="POINT(1.2255 6.1723)",
                bio="Entreprise de transport routier depuis 2015.",
            )
            db.add(profil_proprio)

        # ── Camions ──
        camions_data = [
            ("TG-1234-AB", "Mercedes", "Actros 1845", 2020, TypeCamion.porteur, 20.0, EtatCamion.excellent),
            ("TG-5678-CD", "Volvo", "FH16 500", 2019, TypeCamion.semi_remorque, 25.0, EtatCamion.bon),
            ("TG-9012-EF", "Scania", "R450", 2021, TypeCamion.citerne, 22.0, EtatCamion.excellent),
        ]
        for imm, marque, modele, annee, type_c, cap, etat in camions_data:
            if not profil_proprio:
                continue
            if await camion_exists(imm):
                print(f"ℹ️  Camion déjà présent : {imm}")
                continue
            camion = Camion(
                id=uuid.uuid4(),
                proprietaire_id=profil_proprio.id,
                immatriculation=imm,
                marque=marque,
                modele=modele,
                annee=annee,
                type_camion=type_c,
                capacite_charge=cap,
                etat=etat,
                description=f"Camion {marque} {modele} en excellent état.",
            )
            db.add(camion)

        # ── Mécaniciens fictifs ──
        mecaniciens_data = [
            ("Amadou Méca", "amadou.meca@email.com", ["Mécanique générale"], "POINT(1.2234 6.1675)", "Disponible", "Payant"),
            ("Kossi Motors", "kossi.motors@email.com", ["Électricité auto"], "POINT(0.0233 9.5500)", "Disponible", "Sur devis"),
            ("Fatima Express", "fatima.express@email.com", ["Pneumatique"], "POINT(1.1333 8.9833)", "Occupé", "Gratuit"),
            ("Ibrahim Pro", "ibrahim.pro@email.com", ["Carrosserie", "Soudure"], "POINT(1.3000 7.7500)", "Disponible", "Payant"),
            ("Youssouf Auto", "youssouf.auto@email.com", ["Diagnostic électronique"], "POINT(1.2400 6.1700)", "Disponible", "Payant"),
        ]
        for nom, email, spec, loc, disp, tarif in mecaniciens_data:
            if await user_exists(email):
                print(f"ℹ️  Mécanicien déjà présent : {email}")
                continue
            meca_user = User(
                id=uuid.uuid4(),
                email=email,
                password_hash=bcrypt.hash("Meca@123"),
                nom_complet=nom,
                telephone="+22893456789",
                role=UserRole.mecanicien,
                is_verified=True,
                is_active=True,
            )
            db.add(meca_user)

            profil_meca = ProfilMecanicien(
                id=uuid.uuid4(),
                user_id=meca_user.id,
                specialites=spec,
                annees_experience=8,
                certifications=["Certificat professionnel"],
                tarification=tarif,
                disponibilite=disp,
                localisation=loc,
                rayon_intervention=30,
                bio=f"Mécanicien spécialisé en {spec[0]}.",
            )
            db.add(profil_meca)

        await db.commit()
        print("✅ Données de démonstration insérées avec succès !")
        print("   - 1 Admin")
        print("   - 1 Chauffeur")
        print("   - 1 Propriétaire (3 camions)")
        print("   - 5 Mécaniciens fictifs")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
