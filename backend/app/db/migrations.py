from __future__ import annotations

from pathlib import Path
from alembic import command
from alembic.config import Config

from backend.app.core.config import settings


def get_alembic_config(db_url: str | None = None) -> Config:
    """Create Alembic Config object pointing to backend/alembic.ini."""
    backend_dir = Path(__file__).resolve().parent.parent.parent
    ini_path = backend_dir / "alembic.ini"
    alembic_dir = backend_dir / "alembic"

    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(alembic_dir))
    url = db_url or settings.get_database_url()
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def run_upgrade_head(db_url: str | None = None) -> None:
    """Run all pending migrations to head."""
    cfg = get_alembic_config(db_url)
    command.upgrade(cfg, "head")


def run_downgrade(revision: str = "base", db_url: str | None = None) -> None:
    """Downgrade migrations to target revision."""
    cfg = get_alembic_config(db_url)
    command.downgrade(cfg, revision)


def run_stamp_head(db_url: str | None = None) -> None:
    """Stamp the database as current with head without running SQL (for existing databases)."""
    cfg = get_alembic_config(db_url)
    command.stamp(cfg, "head")
