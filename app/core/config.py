from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


ENV_FILE_PATH = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE_PATH),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    PROJECT_NAME: str = "AS9100D ERP Backend"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "postgresql+pg8000://postgres:Root123@localhost:5433/as9100d_erp"

    JWT_SECRET_KEY: str = "change_me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    RESET_PASSWORD_TOKEN_EXPIRE_MINUTES: int = 30
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 60
    AUTH_LOGIN_MAX_REQUESTS: int = 10
    AUTH_REFRESH_MAX_REQUESTS: int = 20
    AUTH_MAX_ACTIVE_SESSIONS: int = 5
    AUTH_RATE_LIMIT_BACKEND: str = "memory"
    AUTH_RATE_LIMIT_REDIS_URL: str | None = None

    # Password reset email settings
    FRONTEND_RESET_PASSWORD_URL: str | None = None
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_FROM_EMAIL: str | None = None
    SMTP_USE_TLS: bool = True

    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str | None = None
    GOOGLE_ADMIN_EMAILS: str | None = None
    ADMIN_BOOTSTRAP_USERNAME: str = "admin"
    ADMIN_BOOTSTRAP_EMAIL: str = "admin@example.com"
    ADMIN_BOOTSTRAP_PASSWORD: str = "Admin@12345"


settings = Settings()