from pydantic_settings import BaseSettings # type: ignore
from functools import lru_cache


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql://togotruck:togotruck_secret_2026@localhost:5432/togotruckconnect"
    database_url_async: str = "postgresql+asyncpg://togotruck:togotruck_secret_2026@localhost:5432/togotruckconnect"

    # JWT
    jwt_secret_key: str = "togotruck_secret_key_2026_change_in_production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = "TogoTruckConnect <noreply@togotruckconnect.com>"

    # MinIO
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "togotruck_minio"
    minio_secret_key: str = "togotruck_minio_2026"
    minio_bucket: str = "togotruck-uploads"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # App
    next_public_api_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
