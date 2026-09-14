from __future__ import annotations

import sqlite3
from typing import Optional
from fastapi import APIRouter, Depends, Query

from backend.app.db.session import get_db
from backend.app.db.repository import Repository
from backend.app.schemas.domains import TopDomainItem, DnsStatsResponse

router = APIRouter(tags=["Domains & Statistics"])


@router.get(
    "/domains/top",
    response_model=list[TopDomainItem],
    summary="Top Queried Domains",
    description="Retrieve the most frequently requested domains, optionally filtered by a specific device.",
)
def get_top_domains(
    device_id: Optional[str] = Query(None, description="Optional device ID filter"),
    limit: int = Query(20, ge=1, le=100, description="Max number of top domains to return"),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[TopDomainItem]:
    return Repository.get_top_domains(conn, device_id=device_id, limit=limit)


@router.get(
    "/dns/stats",
    response_model=DnsStatsResponse,
    summary="DNS Monitoring Statistics",
    description="Overall DNS metrics: query counts, visibility breakdown, and private DNS bypass ratio.",
)
def get_dns_stats(
    conn: sqlite3.Connection = Depends(get_db),
) -> DnsStatsResponse:
    return Repository.get_dns_stats(conn)
