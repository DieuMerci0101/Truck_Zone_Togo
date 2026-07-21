from fastapi import FastAPI # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
from contextlib import asynccontextmanager

from app.config import get_settings
from app.database import init_db, close_db
from app.routers import auth, chauffeurs, proprietaires, mecaniciens, conversations, incidents, admin, notifications
from app.websocket_chat import router as ws_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialiser les ressources
    yield

    # Libérer les ressources
    await close_db()

app = FastAPI(
    title="Togo Truck Connect API",
    description="API de mise en relation dans le secteur du transport routier au Togo",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
app.include_router(ws_router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "Togo Truck Connect API"}

@app.get("/")
async def root():
    return {"status": "ok", "message": "TogoTruckConnect API"}