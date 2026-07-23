#!/usr/bin/env python3
"""
Script pour vérifier les données dans PostgreSQL.
Usage: venv/bin/python check_db.py
"""
import asyncio
from app.database import async_session
from app.models.user import User
from app.models.chauffeur import ProfilChauffeur
from app.models.proprietaire import ProfilProprietaire
from app.models.mecanicien import ProfilMecanicien
from app.models.camion import Camion
from app.models.offre import OffreRecrutement
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.incident import Incident
from app.models.document import Document
from app.models.notification import Notification
from sqlalchemy import select, func


async def show_data():
    async with async_session() as db:
        print("=" * 60)
        print("  TOGO TRUCK CONNECT — État de la base de données")
        print("=" * 60)

        # Users
        users = (await db.execute(select(User))).scalars().all()
        print(f"\n👤 UTILISATEURS ({len(users)})")
        print("-" * 60)
        for u in users:
            role = u.role.value if hasattr(u.role, "value") else u.role
            print(f"  {u.nom_complet:25s} | {u.email:35s} | {role:15s} | actif={u.is_active}")

        # Profils Chauffeur
        chauffeurs = (await db.execute(select(ProfilChauffeur))).scalars().all()
        print(f"\n🚗 PROFILS CHAUFFEURS ({len(chauffeurs)})")
        print("-" * 60)
        for c in chauffeurs:
            disp = c.disponibilite.value if hasattr(c.disponibilite, "value") else c.disponibilite
            print(f"  Permis: {c.numero_permis:20s} | Exp: {c.annees_experience} ans | {disp}")

        # Profils Proprietaire
        proprios = (await db.execute(select(ProfilProprietaire))).scalars().all()
        print(f"\n🏢 PROFILS PROPRIÉTAIRES ({len(proprios)})")
        print("-" * 60)
        for p in proprios:
            print(f"  {p.nom_entreprise or 'N/A':30s} | {p.adresse}")

        # Profils Mecanicien
        mecas = (await db.execute(select(ProfilMecanicien))).scalars().all()
        print(f"\n🔧 PROFILS MÉCANICIENS ({len(mecas)})")
        print("-" * 60)
        for m in mecas:
            print(f"  Exp: {m.annees_experience} ans | Rayon: {m.rayon_intervention} km | {m.specialites}")

        # Camions
        camions = (await db.execute(select(Camion))).scalars().all()
        print(f"\n🚛 CAMIONS ({len(camions)})")
        print("-" * 60)
        for c in camions:
            print(f"  {c.immatriculation} | {c.marque} {c.modele} | {c.annee} | {c.type_camion}")

        # Offres
        offres = (await db.execute(select(OffreRecrutement))).scalars().all()
        print(f"\n📋 OFFRES ({len(offres)})")
        print("-" * 60)
        for o in offres:
            statut = o.statut.value if hasattr(o.statut, "value") else o.statut
            print(f"  {o.titre[:40]:40s} | {o.salaire_propose} FCFA | {statut}")

        # Conversations & Messages
        convs = (await db.execute(select(Conversation))).scalars().all()
        msgs = (await db.execute(select(Message))).scalars().all()
        print(f"\n💬 MESSAGERIE ({len(convs)} conversations, {len(msgs)} messages)")
        print("-" * 60)

        # Documents
        docs = (await db.execute(select(Document))).scalars().all()
        print(f"\n📄 DOCUMENTS ({len(docs)})")
        print("-" * 60)
        for d in docs:
            statut = d.statut.value if hasattr(d.statut, "value") else d.statut
            print(f"  {d.type_document} | {statut} | {d.fichier_url}")

        # Incidents
        incidents = (await db.execute(select(Incident))).scalars().all()
        print(f"\n⚠️  INCIDENTS ({len(incidents)})")
        print("-" * 60)
        for i in incidents:
            grav = i.gravite.value if hasattr(i.gravite, "value") else i.gravite
            print(f"  {i.type_incident} | {grav} | {i.description[:50]}")

        # Notifications
        notifs = (await db.execute(select(Notification))).scalars().all()
        print(f"\n🔔 NOTIFICATIONS ({len(notifs)})")
        print("-" * 60)
        for n in notifs:
            print(f"  {n.titre[:30]:30s} | lu={n.lu}")

        print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(show_data())
