"""
Script pour créer la base PostgreSQL.
Usage: python -m app.create_database
"""
import subprocess
import sys


def create_database():
    print("🔧 Création de la base PostgreSQL...")

    # Paramètres de connexion
    DB_NAME = "togotruckconnect"
    DB_USER = "togotruck"
    DB_PASSWORD = "togotruck_secret_2026"

    try:
        # Créer l'utilisateur
        subprocess.run(
            ["sudo", "-u", "postgres", "psql", "-c",
             f"CREATE USER {DB_USER} WITH PASSWORD '{DB_PASSWORD}';"],
            capture_output=True, text=True
        )
    except Exception:
        pass

    try:
        # Créer la base
        subprocess.run(
            ["sudo", "-u", "postgres", "psql", "-c",
             f"CREATE DATABASE {DB_NAME} OWNER {DB_USER};"],
            capture_output=True, text=True
        )
        print(f"✅ Base '{DB_NAME}' créée !")
    except Exception as e:
        print(f"⚠️  Base peut-être déjà existante: {e}")

    try:
        # Activer l'extension PostGIS
        subprocess.run(
            ["sudo", "-u", "postgres", "psql", "-d", DB_NAME, "-c",
             "CREATE EXTENSION IF NOT EXISTS postgis;"],
            capture_output=True, text=True
        )
        print("✅ Extension PostGIS activée !")
    except Exception:
        pass

    print("\n📋 Commandes SQL manuelles si besoin :")
    print(f"   sudo -u postgres psql")
    print(f"   CREATE USER {DB_USER} WITH PASSWORD '{DB_PASSWORD}';")
    print(f"   CREATE DATABASE {DB_NAME} OWNER {DB_USER};")
    print(f"   \\c {DB_NAME}")
    print(f"   CREATE EXTENSION IF NOT EXISTS postgis;")


if __name__ == "__main__":
    create_database()
