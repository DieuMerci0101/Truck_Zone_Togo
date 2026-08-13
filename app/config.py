from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Charge automatiquement les variables du fichier .env
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # ==========================
    # Database
    # ==========================
    database_url: str = "postgresql://togotruck:togotruck_secret_2026@localhost:5432/togotruckconnect"

    database_url_async: str = "postgresql+asyncpg://togotruck:togotruck_secret_2026@localhost:5432/togotruckconnect"

    @field_validator("database_url_async", mode="before")
    @classmethod
    def normalize_async_url(cls, v: str) -> str:
        """
        Render (et d'autres hebergeurs) fournissent parfois l'URL de la base
        au format 'postgres://' ou 'postgresql://' (sans le driver asyncpg).
        SQLAlchemy async a besoin du scheme 'postgresql+asyncpg://'.
        Ce validator corrige automatiquement le scheme si besoin.
        """
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and "+asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_sync_url(cls, v: str) -> str:
        """
        Normalise aussi l'URL sync (utilisee par ex. par Alembic) au cas ou
        elle serait fournie avec le scheme legacy 'postgres://'.
        """
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql://", 1)
        return v

    # ==========================
    # JWT
    # ==========================
    jwt_secret_key: str = "togotruck_secret_key_2026_change_in_production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # ==========================
    # SMTP
    # Les variables MAIL_* (Render) et SMTP_* sont toutes acceptées.
    # ==========================
    smtp_host: str = Field(
        default="smtp.gmail.com",
        validation_alias=AliasChoices("smtp_host", "SMTP_HOST", "MAIL_SERVER", "MAIL_HOST"),
    )
    smtp_port: int = Field(
        default=587,
        validation_alias=AliasChoices("smtp_port", "SMTP_PORT", "MAIL_PORT"),
    )
    smtp_user: str = Field(
        default="patgodson01@gmail.com",
        validation_alias=AliasChoices("smtp_user", "SMTP_USER", "SMTP_USERNAME", "MAIL_USERNAME", "MAIL_USER"),
    )
    # Mot de passe : JAMAIS de valeur par défaut codée en dur. Fournir via
    # l'environnement (`.env` en dev, variables Render en prod) :
    #   MAIL_PASSWORD / SMTP_PASSWORD = mot de passe d'application Gmail.
    smtp_password: str = Field(
        default="",
        validation_alias=AliasChoices("smtp_password", "SMTP_PASSWORD", "SMTP_PASS", "MAIL_PASSWORD", "MAIL_PASS"),
    )
    email_from: str = Field(
        # Si vide, l'email est envoyé depuis `smtp_user` (MAIL_USERNAME / SMTP_USER).
        # Avec Gmail, utiliser l'adresse du compte authentifié améliore la
        # délivrabilité (SPF/DKIM alignés) — éviter les domaines tiers.
        # Accepte EMAIL_FROM, MAIL_FROM, SMTP_FROM (doc de déploiement) ou MAIL_DEFAULT_SENDER.
        default="patgodson01@gmail.com",
        validation_alias=AliasChoices("email_from", "EMAIL_FROM", "MAIL_FROM", "SMTP_FROM", "MAIL_DEFAULT_SENDER"),
    )

    # ==========================
    # MinIO
    # ==========================
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "togotruck_minio"
    minio_secret_key: str = "togotruck_minio_2026"
    minio_bucket: str = "togotruck-uploads"

    # ==========================
    # Redis
    # ==========================
    redis_url: str = "redis://localhost:6379/0"

    # ==========================
    # API
    # ==========================
    next_public_api_url: str = "https://truck-zone-togo.onrender.com"

    # ==========================
    # Frontend — URL publique utilisée dans les emails et redirections.
    # Surchargée par la variable d'environnement `FRONTEND_URL`.
    # ==========================
    frontend_url: str = "https://frontend-truck-zone-togo.vercel.app"

    # ==========================
    # CORS — origines autorisées
    # Liste séparée par des virgules (env `ALLOWED_ORIGINS`), ou valeurs par
    # défaut : frontend Vercel de production + environnements locaux.
    # ==========================
    allowed_origins: str = (
        "https://frontend-truck-zone-togo.vercel.app,"
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "https://truck-zone-togo.onrender.com"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()