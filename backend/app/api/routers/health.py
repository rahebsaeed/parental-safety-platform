from __future__ import annotations

import sqlite3
from fastapi import APIRouter, Depends
from backend.app.db.session import get_db
from backend.app.db.repository import Repository
from backend.app.schemas.health import HealthResponse

router = APIRouter(tags=["Health & Status"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Platform Health Status",
    description="Returns platform health, database connectivity, and daemon status.",
)
def get_health(conn: sqlite3.Connection = Depends(get_db)) -> HealthResponse:
    return Repository.check_health(conn)
