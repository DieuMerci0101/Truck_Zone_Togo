import logging
import uuid

from fastapi import FastAPI # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from contextlib import asynccontextmanager

from app.config import get_settings
from app.database import init_db, close_db, async_session
from fastapi.staticfiles import StaticFiles
from app.routers import auth, chauffeurs, proprietaires, mecaniciens, conversations, incidents, admin, notifications, offres, users
from app.websocket_chat import router as ws_router

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()

    try:
        from app.models.user import User
        from app.models.enums import UserRole
        from sqlalchemy import select, func
        from passlib.hash import bcrypt

        async with async_session() as db:
            result = await db.execute(
                select(func.count()).select_from(User).where(User.role == UserRole.admin)
            )
            admin_count = result.scalar()
            if admin_count == 0:
                password_hash = bcrypt.hash("Admin@2026")
                admin_user = User(
                    id=uuid.uuid4(),
                    email="admin@togotruckconnect.com",
                    password_hash=password_hash,
                    nom_complet="Admin TogoTruck",
                    telephone="+22890123456",
                    role=UserRole.admin,
                    is_verified=True,
                    is_active=True,
                )
                db.add(admin_user)
                await db.commit()
                logger.info("✅ Compte admin par défaut créé: admin@togotruckconnect.com")
            else:
                logger.info("ℹ️  Compte admin déjà existant, skip création")
    except Exception as e:
        logger.warning(f"⚠️  Erreur création admin (non bloquant): {e}")

    yield

    await close_db()


app = FastAPI(
    title="Togo Truck Connect API",
    description="API de mise en relation dans le secteur du transport routier au Togo",
    version="1.0.0",
    lifespan=lifespan,
)

ALLOWED_ORIGINS = [
    "http://localhost:3000",
    
    "https://truck-zone-togo.onrender.com",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=r"https://.*\.onrender\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(chauffeurs.router)
app.include_router(proprietaires.router)
app.include_router(mecaniciens.router)
app.include_router(conversations.router)
app.include_router(incidents.router)
app.include_router(admin.router)
app.include_router(notifications.router)
app.include_router(offres.router)
app.include_router(users.router)
app.include_router(ws_router)

app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Togo Truck Connect API"}

@app.get("/")
async def root():
    return {"status": "ok", "message": "TogoTruckConnect API"}
