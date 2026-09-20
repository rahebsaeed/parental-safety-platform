"""Repository layer for analytics aggregations and data export."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import func, distinct, case, Integer, cast, or_
from sqlalchemy.orm import Session

from backend.app.classifiers.traffic_tags import (
    SEARCH_ENGINES,
    match_search_engine,
    search_engine_label,
)
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
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
) -> dict:
    """Summary overview metrics for the network or a specific device."""
    q_base = session.query(DnsQuery)
    if device_id:
        q_base = q_base.filter(DnsQuery.device_id == device_id)
    if start_time:
        q_base = q_base.filter(DnsQuery.occurred_at >= start_time)
    if end_time:
        q_base = q_base.filter(DnsQuery.occurred_at <= end_time)

    total_queries = q_base.count()
    distinct_domains = q_base.with_entities(func.count(distinct(DnsQuery.domain)))
    total_domains = distinct_domains.scalar() or 0

    active_devices = (
        q_base.with_entities(func.count(distinct(DnsQuery.device_id)))
        .filter(DnsQuery.device_id.isnot(None))
        .scalar()
        or 0
    )

    # Top category
    cat_dist = get_category_distribution(session, device_id=device_id, start_time=start_time, end_time=end_time)
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


# ---------------------------------------------------------------------------
# Search Engine Activity (domain-level visits — keywords are NOT in DNS)
# ---------------------------------------------------------------------------

def get_search_engine_activity(
    session: Session,
    device_id: Optional[str] = None,
    days: int = 7,
) -> dict:
    """Which search engines a device used, and when.

    Matches queried domains against SEARCH_ENGINES roots in one query, then
    groups in Python. Returns per-engine summaries plus the most recent
    individual visits. Typed keywords can never appear here: DNS carries
    hostnames only, never URL paths or query strings.
    """
    roots: list[str] = [root for _eid, _label, rr in SEARCH_ENGINES for root in rr]
    like_clauses = []
    for root in roots:
        like_clauses.append(DnsQuery.domain == root)
        like_clauses.append(DnsQuery.domain.like(f"%.{root}"))

    cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, min(days, 90)))).isoformat()

    query = (
        session.query(DnsQuery.domain, DnsQuery.occurred_at)
        .filter(DnsQuery.occurred_at >= cutoff)
        .filter(or_(*like_clauses))
    )
    if device_id:
        query = query.filter(DnsQuery.device_id == device_id)
    rows = (
        query.order_by(DnsQuery.occurred_at.desc(), DnsQuery.id.desc())
        .limit(5000)
        .all()
    )

    per_engine: dict[str, dict] = {}
    visits: list[dict] = []
    for domain, occurred_at in rows:
        engine = match_search_engine(domain)
        if not engine:
            continue
        entry = per_engine.setdefault(engine, {"visits": 0, "last_seen": None})
        entry["visits"] += 1
        if entry["last_seen"] is None:
            entry["last_seen"] = occurred_at
        if len(visits) < 100:
            visits.append(
                {
                    "engine": engine,
                    "label": search_engine_label(engine),
                    "domain": domain,
                    "occurred_at": occurred_at,
                }
            )

    # "Opened next": distinct non-engine domains looked up within 10 minutes
    # after each engine visit — the closest DNS-visible proxy for what the
    # search led to (topics, not keywords).
    opened_next = _opened_after_engine(
        session, visits, device_id=device_id, window_minutes=10, per_engine_limit=5,
    )

    engines = [
        {
            "engine": engine,
            "label": search_engine_label(engine),
            "visits": data["visits"],
            "last_seen": data["last_seen"],
            "opened_next": opened_next.get(engine, []),
        }
        for engine, data in sorted(
            per_engine.items(), key=lambda kv: kv[1]["visits"], reverse=True
        )
    ]
    return {"engines": engines, "visits": visits}


def _parse_iso(value: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _opened_after_engine(
    session: Session,
    visits: list[dict],
    device_id: Optional[str] = None,
    window_minutes: int = 10,
    per_engine_limit: int = 5,
) -> dict[str, list[dict]]:
    """Top non-engine domains queried shortly after engine visits."""
    if not visits:
        return {}
    bounds = []
    for visit in visits:
        start = _parse_iso(visit["occurred_at"])
        if start is None:
            continue
        bounds.append((start, start + timedelta(minutes=window_minutes), visit["engine"]))
    if not bounds:
        return {}
    earliest = min(start for start, _end, _engine in bounds)

    q = session.query(DnsQuery.domain, DnsQuery.occurred_at).filter(
        DnsQuery.occurred_at >= earliest.isoformat()
    )
    if device_id:
        q = q.filter(DnsQuery.device_id == device_id)
    rows = q.order_by(DnsQuery.occurred_at.asc(), DnsQuery.id.asc()).limit(20000).all()

    parsed = []
    for domain, occurred_at in rows:
        moment = _parse_iso(occurred_at)
        if moment is None:
            continue
        parsed.append((moment, domain))

    # Single sorted pass: bounds ascending, one forward pointer over the
    # ascending rows. A later bound starts no earlier, so the pointer
    # never moves backwards; each row is scanned at most twice overall.
    bounds.sort(key=lambda bound: bound[0])
    counts: dict[str, dict[str, int]] = {}
    pos = 0
    total = len(parsed)
    for start, end, engine in bounds:
        while pos < total and parsed[pos][0] <= start:
            pos += 1
        seen_here: set[str] = set()
        cursor = pos
        while cursor < total and parsed[cursor][0] <= end:
            domain = parsed[cursor][1]
            if not match_search_engine(domain):
                seen_here.add(domain)
            cursor += 1
        bucket = counts.setdefault(engine, {})
        for domain in seen_here:
            bucket[domain] = bucket.get(domain, 0) + 1

    return {
        engine: [
            {"domain": domain, "visits": n}
            for domain, n in sorted(bucket.items(), key=lambda kv: kv[1], reverse=True)[
                :per_engine_limit
            ]
        ]
        for engine, bucket in counts.items()
    }
