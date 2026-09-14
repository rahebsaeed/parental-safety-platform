from __future__ import annotations

import sqlite3
from typing import Generator
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session

from backend.app.core.config import settings


def _create_engine_instance():
    url = settings.get_database_url()
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    engine = create_engine(
        url,
        connect_args=connect_args,
        future=True,
    )

    if url.startswith("sqlite"):
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL;")
            cursor.execute("PRAGMA busy_timeout=5000;")
            cursor.execute("PRAGMA foreign_keys=ON;")
            cursor.close()

    return engine


engine = _create_engine_instance()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency yielding an active SQLAlchemy ORM session."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_connection(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create a configured raw SQLite connection.

    Uses row_factory=sqlite3.Row so columns can be accessed by name.
    Configures WAL mode and busy timeout for concurrent safety with collectors.
    """
    path = Path(db_path) if db_path else settings.resolve_database_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def get_db() -> Generator[sqlite3.Connection, None, None]:
    """FastAPI dependency that yields a database connection and closes it."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()
