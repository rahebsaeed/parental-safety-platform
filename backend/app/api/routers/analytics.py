"""Analytics API Router — Phase 7.

GET /api/analytics/overview     — High-level summary metrics
GET /api/analytics/categories   — Category distribution breakdown
GET /api/analytics/active-hours — Hourly distribution of DNS requests (00:00 to 23:59)
GET /api/analytics/timeline     — Daily query trend timeline
GET /api/analytics/export/csv   — CSV file stream export (Section 36)
GET /api/analytics/export/json  — JSON format export (Section 36)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from backend.app.analytics.service import enrich_category_metrics, generate_csv_stream
from backend.app.analytics.types import NETWORK_INDICATOR_DISCLAIMER
from backend.app.db import analytics_repo as repo
from backend.app.db.session import get_session
from backend.app.schemas.analytics import (
    AnalyticsOverviewResponse,
    CategoryDistributionItem,
    CategoryDistributionResponse,
    ExportJsonResponse,
    ExportRecordItem,
    HourlyActivityItem,
    HourlyActivityResponse,
    SearchEngineSummary,
    SearchEngineVisit,
    SearchEnginesResponse,
    TimelineItem,
    TimelineResponse,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=AnalyticsOverviewResponse)
def get_analytics_overview(
    device_id: Optional[str] = Query(None, description="Optional filter by device ID"),
    start_time: Optional[str] = Query(None, description="Start timestamp (ISO-8601)"),
    end_time: Optional[str] = Query(None, description="End timestamp (ISO-8601)"),
    session: Session = Depends(get_session),
) -> AnalyticsOverviewResponse:
    """Return high-level activity overview with mandatory ethical disclaimer."""
    data = repo.get_analytics_overview(session, device_id=device_id, start_time=start_time, end_time=end_time)
    return AnalyticsOverviewResponse(device_id=device_id, **data)


# ---------------------------------------------------------------------------
# Category Distribution
# ---------------------------------------------------------------------------

@router.get("/categories", response_model=CategoryDistributionResponse)
def get_category_distribution(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    start_time: Optional[str] = Query(None, description="Start timestamp (ISO-8601)"),
    end_time: Optional[str] = Query(None, description="End timestamp (ISO-8601)"),
    session: Session = Depends(get_session),
) -> CategoryDistributionResponse:
    """Return DNS query distribution across categories with labels and colors."""
    raw = repo.get_category_distribution(
        session,
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
    )
    enriched = enrich_category_metrics(raw)
    total_queries = sum(item["query_count"] for item in enriched)

    items = [CategoryDistributionItem(**item) for item in enriched]
    return CategoryDistributionResponse(
        device_id=device_id,
        total_queries=total_queries,
        categories=items,
    )


# ---------------------------------------------------------------------------
# Active Hours (Time of Day 00:00 to 23:59)
# ---------------------------------------------------------------------------

@router.get("/active-hours", response_model=HourlyActivityResponse)
def get_active_hours(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    start_time: Optional[str] = Query(None, description="Start timestamp (ISO-8601)"),
    end_time: Optional[str] = Query(None, description="End timestamp (ISO-8601)"),
    session: Session = Depends(get_session),
) -> HourlyActivityResponse:
    """Return 24-hour histogram of DNS request volume (00:00 to 23:59)."""
    raw = repo.get_hourly_activity(
        session,
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
    )
    items = [HourlyActivityItem(**item) for item in raw]
    return HourlyActivityResponse(
        device_id=device_id,
        hourly_distribution=items,
    )


# ---------------------------------------------------------------------------
# Daily Timeline
# ---------------------------------------------------------------------------

@router.get("/timeline", response_model=TimelineResponse)
def get_activity_timeline(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    days: int = Query(14, ge=1, le=90, description="Number of days to inspect"),
    session: Session = Depends(get_session),
) -> TimelineResponse:
    """Return daily DNS request volume trend."""
    raw = repo.get_daily_timeline(session, device_id=device_id, days=days)
    items = [TimelineItem(**item) for item in raw]
    return TimelineResponse(
        device_id=device_id,
        timeline=items,
    )


# ---------------------------------------------------------------------------
# Search Engine Activity (domain-level visits)
# ---------------------------------------------------------------------------

@router.get("/search-engines", response_model=SearchEnginesResponse)
def get_search_engines(
    device_id: Optional[str] = Query(None, description="Filter by device ID (per-child view)"),
    days: int = Query(7, ge=1, le=90, description="Lookback window in days"),
    session: Session = Depends(get_session),
) -> SearchEnginesResponse:
    """Which search engines were used, and when.

    DNS carries hostnames only — never the typed keywords — so this
    reports engine visits (counts + timestamps), not search terms.
    """
    data = repo.get_search_engine_activity(session, device_id=device_id, days=days)
    return SearchEnginesResponse(
        device_id=device_id,
        engines=[SearchEngineSummary(**e) for e in data["engines"]],
        visits=[SearchEngineVisit(**v) for v in data["visits"]],
    )


# ---------------------------------------------------------------------------
# Data Export: CSV (Section 36)
# ---------------------------------------------------------------------------

@router.get("/export/csv")
def export_csv(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    start_time: Optional[str] = Query(None, description="Start timestamp filter"),
    end_time: Optional[str] = Query(None, description="End timestamp filter"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(10000, ge=1, le=50000),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    """Stream DNS query records as a downloadable CSV file."""
    records = repo.export_dns_records(
        session,
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
        category=category,
        limit=limit,
    )
    generator = generate_csv_stream(records)

    filename = f"dns_activity_export_{device_id or 'all'}.csv"
    return StreamingResponse(
        generator,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Data Export: JSON (Section 36)
# ---------------------------------------------------------------------------

@router.get("/export/json", response_model=ExportJsonResponse)
def export_json(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    start_time: Optional[str] = Query(None, description="Start timestamp filter"),
    end_time: Optional[str] = Query(None, description="End timestamp filter"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(5000, ge=1, le=20000),
    session: Session = Depends(get_session),
) -> ExportJsonResponse:
    """Download DNS records formatted as structured JSON with disclaimer."""
    records = repo.export_dns_records(
        session,
        device_id=device_id,
        start_time=start_time,
        end_time=end_time,
        category=category,
        limit=limit,
    )
    items = [ExportRecordItem(**r) for r in records]
    return ExportJsonResponse(
        record_count=len(items),
        records=items,
    )
