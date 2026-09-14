"""Repository layer for analytics aggregations and data export."""
from __future__ import annotations

from typing import Optional
from sqlalchemy import func, distinct, case, Integer, cast
from sqlalchemy.orm import Session

from backend.app.models.device import Device
from backend.app.models.dns import DnsQuery
from backend.app.models.classification import DomainClassification


# ---------------------------------------------------------------------------
# Category Distribution
# ---------------------------------------------------------------------------

def get_category_distribution(
    session: Session,
    device_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> list[dict]:
    """Calculate query volume and distinct domain count grouped by category."""
    cat_col = func.coalesce(DomainClassification.category, "UNCATEGORIZED").label("category")

    q = (
        session.query(
            cat_col,
            func.count(DnsQuery.id).label("query_count"),
            func.count(distinct(DnsQuery.domain)).label("distinct_domains"),
        )
        .outerjoin(DomainClassification, DnsQuery.domain == DomainClassification.domain)
    )

    if device_id:
        q = q.filter(DnsQuery.device_id == device_id)
    if start_time:
        q = q.filter(DnsQuery.occurred_at >= start_time)
    if end_time:
        q = q.filter(DnsQuery.occurred_at <= end_time)

    rows = q.group_by(cat_col).order_by(func.count(DnsQuery.id).desc()).all()

    total_queries = sum(r.query_count for r in rows) or 1

    return [
        {
            "category": r.category,
            "query_count": r.query_count,
            "distinct_domains": r.distinct_domains,
            "percentage": round((r.query_count / total_queries) * 100, 2),
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Hourly Activity (00:00 to 23:59)
# ---------------------------------------------------------------------------

def get_hourly_activity(
    session: Session,
    device_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> list[dict]:
    """Aggregate query counts by hour of day (0 to 23)."""
    # Substr extraction handles both 'YYYY-MM-DD HH:MM:SS' and 'YYYY-MM-DDTHH:MM:SS'
    hour_expr = cast(func.substr(DnsQuery.occurred_at, 12, 2), Integer).label("hour")

    q = session.query(
        hour_expr,
        func.count(DnsQuery.id).label("query_count"),
    )

    if device_id:
        q = q.filter(DnsQuery.device_id == device_id)
    if start_time:
        q = q.filter(DnsQuery.occurred_at >= start_time)
    if end_time:
        q = q.filter(DnsQuery.occurred_at <= end_time)

    rows = q.group_by(hour_expr).all()
    counts_by_hour = {r.hour: r.query_count for r in rows if r.hour is not None}

    # Ensure all 24 hours are represented
    return [{"hour": h, "query_count": counts_by_hour.get(h, 0)} for h in range(24)]


# ---------------------------------------------------------------------------
# Daily Timeline
# ---------------------------------------------------------------------------

def get_daily_timeline(
    session: Session,
    device_id: Optional[str] = None,
    days: int = 14,
) -> list[dict]:
    """Aggregate queries by date (YYYY-MM-DD) over recent days."""
    date_expr = func.substr(DnsQuery.occurred_at, 1, 10).label("date")

    q = session.query(
        date_expr,
        func.count(DnsQuery.id).label("query_count"),
        func.count(distinct(DnsQuery.device_id)).label("active_devices_count"),
    )

    if device_id:
        q = q.filter(DnsQuery.device_id == device_id)

    rows = q.group_by(date_expr).order_by(date_expr.asc()).limit(days).all()

    return [
        {
            "date": r.date,
            "query_count": r.query_count,
            "active_devices_count": r.active_devices_count,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# Overview Metrics
# ---------------------------------------------------------------------------

def get_analytics_overview(
    session: Session,
    device_id: Optional[str] = None,
) -> dict:
    """Summary overview metrics for the network or a specific device."""
    q_base = session.query(DnsQuery)
    if device_id:
        q_base = q_base.filter(DnsQuery.device_id == device_id)

    total_queries = q_base.count()
    distinct_domains = session.query(func.count(distinct(DnsQuery.domain)))
    if device_id:
        distinct_domains = distinct_domains.filter(DnsQuery.device_id == device_id)
    total_domains = distinct_domains.scalar() or 0

    active_devices = (
        session.query(func.count(distinct(DnsQuery.device_id)))
        .filter(DnsQuery.device_id.isnot(None))
        .scalar()
        or 0
    )

    # Top category
    cat_dist = get_category_distribution(session, device_id=device_id)
    top_category = cat_dist[0]["category"] if cat_dist else "UNCATEGORIZED"

    return {
        "total_queries": total_queries,
        "distinct_domains": total_domains,
        "active_devices": active_devices,
        "top_category": top_category,
    }


# ---------------------------------------------------------------------------
# Data Export Query (Section 36)
# ---------------------------------------------------------------------------

def export_dns_records(
    session: Session,
    device_id: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 10000,
) -> list[dict]:
    """Query raw DNS activity joined with device names and categories for export."""
    cat_col = func.coalesce(DomainClassification.category, "UNCATEGORIZED").label("category")

    q = (
        session.query(
            DnsQuery.id,
            DnsQuery.occurred_at,
            DnsQuery.source_ip,
            DnsQuery.device_id,
            Device.friendly_name.label("device_name"),
            DnsQuery.domain,
            cat_col,
            DnsQuery.query_type,
            DnsQuery.response_status,
            DnsQuery.dns_visibility,
        )
        .outerjoin(Device, DnsQuery.device_id == Device.device_id)
        .outerjoin(DomainClassification, DnsQuery.domain == DomainClassification.domain)
    )

    if device_id:
        q = q.filter(DnsQuery.device_id == device_id)
    if start_time:
        q = q.filter(DnsQuery.occurred_at >= start_time)
    if end_time:
        q = q.filter(DnsQuery.occurred_at <= end_time)
    if category:
        q = q.filter(cat_col == category.upper())

    rows = q.order_by(DnsQuery.occurred_at.desc(), DnsQuery.id.desc()).limit(limit).all()

    return [
        {
            "id": r.id,
            "occurred_at": r.occurred_at,
            "source_ip": r.source_ip,
            "device_id": r.device_id or "",
            "device_name": r.device_name or "Unknown Device",
            "domain": r.domain,
            "category": r.category,
            "query_type": r.query_type,
            "response_status": r.response_status,
            "dns_visibility": r.dns_visibility,
        }
        for r in rows
    ]
