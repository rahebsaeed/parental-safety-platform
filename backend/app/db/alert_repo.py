"""Repository layer for Safety Alerts."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.alerts.engine import evaluate, generate_dedup_key
from backend.app.alerts.types import AlertStatus, DetectionResult
from backend.app.models.alert import SafetyAlert
from backend.app.models.classification import DomainClassification
from backend.app.models.dns import DnsQuery


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_iso(ts: str) -> datetime:
    try:
        # Handle space separator or T separator
        clean_ts = ts.replace(" ", "T")
        dt = datetime.fromisoformat(clean_ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Write / Deduplication
# ---------------------------------------------------------------------------

def create_or_dedup_alert(
    session: Session,
    device_id: Optional[str],
    domain: str,
    detection: DetectionResult,
    cooldown_seconds: int = 3600,
    occurred_at: Optional[str] = None,
) -> tuple[SafetyAlert, bool]:
    """Create a new alert or aggregate with an active existing alert.

    Returns:
        (alert, is_new: bool)
    """
    ts = occurred_at or _now_iso()
    dedup_key = generate_dedup_key(device_id, detection.alert_type.value, domain)

    # Search for an active alert with the same deduplication key
    existing: SafetyAlert | None = (
        session.query(SafetyAlert)
        .filter(
            SafetyAlert.dedup_key == dedup_key,
            SafetyAlert.status == AlertStatus.ACTIVE.value,
        )
        .order_by(SafetyAlert.id.desc())
        .first()
    )

    if existing:
        last_seen_dt = _parse_iso(existing.last_seen_at)
        curr_dt = _parse_iso(ts)
        diff_sec = abs((curr_dt - last_seen_dt).total_seconds())

        if diff_sec <= cooldown_seconds:
            # Aggregate into existing alert
            existing.occurrence_count += 1
            existing.last_seen_at = ts
            return existing, False

    # Create new alert
    alert = SafetyAlert(
        device_id=device_id,
        domain=domain,
        alert_type=detection.alert_type.value,
        severity=detection.severity.value,
        title=detection.title,
        description=detection.description,
        rule_matched=detection.rule_matched,
        explanation=detection.explanation,
        status=AlertStatus.ACTIVE.value,
        occurrence_count=1,
        dedup_key=dedup_key,
        created_at=ts,
        last_seen_at=ts,
    )
    session.add(alert)
    session.flush()
    return alert, True


# ---------------------------------------------------------------------------
# Query / Read
# ---------------------------------------------------------------------------

def list_alerts(
    session: Session,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    device_id: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[SafetyAlert]:
    """Query safety alerts with optional filtering."""
    q = session.query(SafetyAlert)
    if status:
        q = q.filter(SafetyAlert.status == status.upper())
    if severity:
        q = q.filter(SafetyAlert.severity == severity.upper())
    if device_id:
        q = q.filter(SafetyAlert.device_id == device_id)
    if domain:
        q = q.filter(SafetyAlert.domain == domain.strip().lower().rstrip("."))

    return q.order_by(SafetyAlert.last_seen_at.desc(), SafetyAlert.id.desc()).offset(offset).limit(limit).all()


def get_alert(session: Session, alert_id: int) -> Optional[SafetyAlert]:
    """Fetch an alert by primary key."""
    return session.get(SafetyAlert, alert_id)


def update_alert_status(
    session: Session,
    alert_id: int,
    status: str | AlertStatus,
) -> Optional[SafetyAlert]:
    """Transition the status of an alert (e.g. ACKNOWLEDGED, DISMISSED, RESOLVED)."""
    status_str = status.value if isinstance(status, AlertStatus) else str(status).upper()
    alert = session.get(SafetyAlert, alert_id)
    if not alert:
        return None
    alert.status = status_str
    return alert


def get_alert_summary(session: Session) -> dict:
    """Aggregate statistics on safety alerts."""
    total = session.query(func.count(SafetyAlert.id)).scalar() or 0
    active = session.query(func.count(SafetyAlert.id)).filter(SafetyAlert.status == AlertStatus.ACTIVE.value).scalar() or 0

    # Severity breakdown for active alerts
    sev_rows = (
        session.query(SafetyAlert.severity, func.count(SafetyAlert.id))
        .filter(SafetyAlert.status == AlertStatus.ACTIVE.value)
        .group_by(SafetyAlert.severity)
        .all()
    )
    by_severity = {row[0]: row[1] for row in sev_rows}

    # Type breakdown
    type_rows = (
        session.query(SafetyAlert.alert_type, func.count(SafetyAlert.id))
        .group_by(SafetyAlert.alert_type)
        .all()
    )
    by_type = {row[0]: row[1] for row in type_rows}

    return {
        "total_alerts": total,
        "active_alerts": active,
        "by_severity": by_severity,
        "by_type": by_type,
    }


# ---------------------------------------------------------------------------
# Batch Scan Queries
# ---------------------------------------------------------------------------

def scan_queries_for_alerts(session: Session, limit: int = 1000) -> dict:
    """Scan recent DNS queries and generate safety alerts for any hits.

    Returns summary metrics of the scan.
    """
    # Fetch recent queries joined with domain_classifications if available
    queries = (
        session.query(DnsQuery)
        .order_by(DnsQuery.id.desc())
        .limit(limit)
        .all()
    )

    created_count = 0
    aggregated_count = 0

    for q in queries:
        # Check classification table
        dc: DomainClassification | None = session.get(DomainClassification, q.domain)
        cat = dc.category if dc else None

        detection = evaluate(q.domain, category=cat, dns_visibility=q.dns_visibility)
        if detection:
            _, is_new = create_or_dedup_alert(
                session,
                device_id=q.device_id,
                domain=q.domain,
                detection=detection,
                occurred_at=q.occurred_at,
            )
            if is_new:
                created_count += 1
            else:
                aggregated_count += 1

    if created_count or aggregated_count:
        session.flush()

    return {
        "scanned_queries": len(queries),
        "alerts_created": created_count,
        "alerts_aggregated": aggregated_count,
    }
