from __future__ import annotations

import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Parental Safety Platform API"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api"
    
    # Database path / URL resolution:
    # If DATABASE_URL is set (e.g. postgresql://...), it is used directly.
    # Otherwise, falls back to SQLite at DATABASE_PATH or discovery db.
    DATABASE_URL: str = ""
    DATABASE_PATH: str = ""

    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: list[str] = ["*"]

    # Service monitoring paths
    PID_FILE: str = "/run/parental-safety-dnsmasq.pid"
    DNSMASQ_LOG_PATH: str = "/var/log/parental-safety/dnsmasq.log"

    # Security & Authentication (Phase 10)
    PARENT_PASSWORD: str = "admin123"
    AUTH_ENABLED: bool = True
    RATE_LIMIT_ENABLED: bool = True
    SESSION_EXPIRE_HOURS: int = 24

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def resolve_database_path(self) -> Path:
        """Find the real SQLite database file if not explicitly set."""
        if self.DATABASE_PATH:
            return Path(self.DATABASE_PATH).resolve()

        # Potential locations relative to current execution.
        # NOTE: dev runs with cwd=collector/ (so ./data/... is correct
        # there); production runs with cwd=/opt/parental-safety (so the
        # absolute /opt path is required). Never hardcode a $HOME path here.
        candidates = [
            Path("/opt/parental-safety/collector/data/discovery.sqlite3"),
            Path("collector/data/discovery.sqlite3"),
            Path("../collector/data/discovery.sqlite3"),
            Path("data/discovery.sqlite3"),
        ]
        for candidate in candidates:
            if candidate.is_file():
                return candidate.resolve()

        # Default fallback
        return Path("collector/data/discovery.sqlite3").resolve()

    def get_database_url(self) -> str:
        """Return full SQLAlchemy database URL (SQLite or PostgreSQL)."""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"sqlite:///{self.resolve_database_path()}"


settings = Settings()
