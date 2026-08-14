import logging
import os
import uuid

from fastapi import FastAPI # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from contextlib import asynccontextmanager

from app.config import get_settings
from app.database import init_db, close_db, async_session
from fastapi.staticfiles import StaticFiles
from app.routers import auth, chauffeurs, proprietaires, mecaniciens, conversations, incidents, admin, notifications, offres, users, countries, documents, dashboard
from app.websocket_chat import router as ws_router
from app.assistance_events import router as assistance_ws_router

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    try:
        from app.models.user import User
        from app.models.enums import UserRole
        from sqlalchemy import select
        from passlib.hash import bcrypt

        admin_email = "admin@togotruck.com"
        admin_password = "AdminPassword123!"
        legacy_admin_email = "admin@togotruckconnect.com"

        async with async_session() as db:
            # 1) Neutralise l'ancien compte admin (remplacé par le nouveau).
            legacy_result = await db.execute(select(User).where(User.email == legacy_admin_email))
            legacy_user = legacy_result.scalar_one_or_none()
            if legacy_user is not None and legacy_user.email != admin_email:
                legacy_user.is_active = False
                legacy_user.is_verified = False
                legacy_user.role = UserRole.chauffeur
                logger.info("ℹ️  Ancien compte admin désactivé : %s", legacy_admin_email)

            # 2) Crée / répare le compte admin local.
            result = await db.execute(select(User).where(User.email == admin_email))
            admin_user = result.scalar_one_or_none()
            if admin_user is None:
                password_hash = bcrypt.hash(admin_password)
                admin_user = User(
                    id=uuid.uuid4(),
                    email=admin_email,
                    password_hash=password_hash,
                    nom_complet="Admin TogoTruck",
                    telephone="+22890123456",
                    role=UserRole.admin,
                    is_verified=True,
                    is_active=True,
                )
                db.add(admin_user)
                logger.info("✅ Compte admin local créé : admin@togotruck.com")
            else:
                # Sécurise le rôle admin + le mot de passe par défaut (idempotent).
                if admin_user.role != UserRole.admin or not bcrypt.verify(
                    admin_password, admin_user.password_hash
                ):
                    admin_user.role = UserRole.admin
                    admin_user.is_verified = True
                    admin_user.is_active = True
                    admin_user.password_hash = bcrypt.hash(admin_password)
                    logger.info("✅ Compte admin réparé (rôle + mot de passe)")
                else:
                    logger.info("ℹ️  Compte admin déjà présent, skip création")
            await db.commit()
    except Exception as e:
        logger.warning(f"⚠️  Erreur création admin (non bloquant): {e}")

    try:
        from app.utils.seed_countries import countries_data
        from app.models.country import Country
        from sqlalchemy import func

        async with async_session() as db:
            result = await db.execute(select(func.count()).select_from(Country))
            existing = await db.execute(select(Country.code))
            existing_codes = {row[0] for row in existing.all()}
            missing = [
                row for row in countries_data() if row["code"] not in existing_codes
            ]
            if missing:
                db.add_all([Country(**row) for row in missing])
                await db.commit()
                logger.info(
                    f"🌍 {len(missing)} pays manquants insérés (total attendu : {len(countries_data())})"
                )
            else:
                logger.info(
                    f"ℹ️  Table countries à jour ({result.scalar()} pays), skip seeding"
                )
    except Exception as e:
        logger.warning(f"⚠️  Erreur seeding pays (non bloquant): {e}")

    yield

    await close_db()


app = FastAPI(
    title="Togo Truck Connect API",
    description="API de mise en relation dans le secteur du transport routier au Togo",
    version="1.0.0",
    lifespan=lifespan,
)

# Origines CORS autorisées : lues depuis la variable d'environnement
# `ALLOWED_ORIGINS` (liste séparée par des virgules), avec repli sur les
# valeurs par défaut (production Vercel + localhost).
_ALLOWED_ORIGINS_DEFAULT = [
    "https://frontend-truck-zone-togo.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://truck-zone-togo.onrender.com",
]

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", settings.allowed_origins).split(",")
    if origin.strip()
] or _ALLOWED_ORIGINS_DEFAULT

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.(onrender\.com|vercel\.app)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chauffeurs.router)
app.include_router(chauffeurs.alias_router)
app.include_router(proprietaires.router)
app.include_router(mecaniciens.router)
app.include_router(mecaniciens.alias_router)
app.include_router(conversations.router)
app.include_router(conversations.chat_router)
app.include_router(incidents.router)
app.include_router(admin.router)
app.include_router(notifications.router)
app.include_router(offres.router)
app.include_router(users.router)
app.include_router(countries.router)
app.include_router(documents.router)
app.include_router(dashboard.router)
app.include_router(ws_router)
app.include_router(assistance_ws_router)

# Crée les dossiers d'upload avant le montage statique pour éviter un crash
# de démarrage sur Render (filesystem éphémère) et des erreurs d'écriture.
os.makedirs("uploads", exist_ok=True)
for _sub in (
    "documents",
    "justificatifs",
    "camions",
    "audios",
    "photos",
    # Stockage persistant centralisé (jamais purgé automatiquement)
    "permanent/photos",
    "permanent/camions",
    "permanent/documents",
    "permanent/justificatifs",
    "permanent/audios",
):
    os.makedirs(os.path.join("uploads", _sub), exist_ok=True)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Togo Truck Connect API"}

@app.get("/")
async def root():
    return {"status": "ok", "message": "TogoTruckConnect API"}
