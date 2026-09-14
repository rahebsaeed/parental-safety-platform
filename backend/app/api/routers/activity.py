from __future__ import annotations

import sqlite3
from typing import Optional
from fastapi import APIRouter, Depends, Query

from backend.app.db.session import get_db
from backend.app.db.repository import Repository
from backend.app.schemas.activity import PaginatedActivityResponse

router = APIRouter(prefix="/activity", tags=["DNS Activity"])


@router.get(
    "",
    response_model=PaginatedActivityResponse,
    summary="Query DNS Activity Stream",
    description=(
        "Fetch paginated DNS query logs with optional filters by device_id, domain (substring), "
        "query type (A, AAAA, HTTPS), response status (NOERROR, NXDOMAIN), and visibility (FULL, PARTIAL)."
    ),
)
def get_activity(
    device_id: Optional[str] = Query(None, description="Filter by device ID (e.g. dev_03)"),
    domain: Optional[str] = Query(None, description="Search domain containing substring"),
    query_type: Optional[str] = Query(None, description="Filter by query type (A, AAAA, HTTPS, etc.)"),
    response_status: Optional[str] = Query(None, description="Filter by response status (NOERROR, NXDOMAIN, etc.)"),
    visibility: Optional[str] = Query(None, description="Filter by DNS visibility: FULL or PARTIAL"),
    limit: int = Query(50, ge=1, le=500, description="Number of records to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    conn: sqlite3.Connection = Depends(get_db),
) -> PaginatedActivityResponse:
    total, items = Repository.list_activity(
        conn,
        device_id=device_id,
        domain=domain,
        query_type=query_type,
        response_status=response_status,
        dns_visibility=visibility,
        limit=limit,
        offset=offset,
    )
    return PaginatedActivityResponse(
        total=total,
        limit=limit,
        offset=offset,
        items=items,
    )
