"""Safety Alerts API Router — Phase 6.

GET   /api/alerts          — list alerts with filtering
GET   /api/alerts/summary  — alert metrics and counts
POST  /api/alerts/scan     — trigger safety scan on DNS queries
GET   /api/alerts/{id}     — retrieve specific alert with explainability
PATCH /api/alerts/{id}     — update alert status (ACKNOWLEDGED, DISMISSED, RESOLVED)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.app.alerts.types import AlertSeverity, AlertStatus
from backend.app.core.auth import get_client_ip
from backend.app.db import alert_repo as repo
from backend.app.db.session import get_session
from backend.app.models.audit import AuditLog
from backend.app.models.device import Device
from backend.app.schemas.alert import (
    AlertSummaryResponse,
    SafetyAlertRead,
    SafetyAlertUpdate,
    ScanResponse,
)

router = APIRouter(prefix="/alerts", tags=["Safety Alerts"])


def _device_names(session: Session) -> dict[str, str]:
    """Map device_id → display name (friendly name, else the raw ID).

    One query per request keeps alert payloads showing "nasseem phone"
    instead of "dev_07" without N+1 lookups.
    """
    names: dict[str, str] = {}
    for device_id, friendly_name in session.query(Device.device_id, Device.friendly_name).all():
        names[device_id] = friendly_name or device_id
    return names


def _read_alert(alert, names: dict[str, str]) -> SafetyAlertRead:
    payload = SafetyAlertRead.model_validate(alert)
    payload.device_name = names.get(alert.device_id or "", None)
    if payload.device_name is None and alert.device_id:
        payload.device_name = alert.device_id
    return payload


# ---------------------------------------------------------------------------
# List Alerts
# ---------------------------------------------------------------------------

@router.get("", response_model=list[SafetyAlertRead])
def list_alerts(
    status: Optional[str] = Query(None, description="Filter by status: ACTIVE, ACKNOWLEDGED, DISMISSED, RESOLVED"),
    severity: Optional[str] = Query(None, description="Filter by severity: CRITICAL, HIGH, MEDIUM, LOW"),
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    domain: Optional[str] = Query(None, description="Filter by exact domain (used by the activity inspector)"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[SafetyAlertRead]:
    """Retrieve safety alerts ordered by most recent occurrence."""
    rows = repo.list_alerts(
        session,
        status=status,
        severity=severity,
        device_id=device_id,
        domain=domain,
        limit=limit,
        offset=offset,
    )
    names = _device_names(session)
    return [_read_alert(r, names) for r in rows]


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=AlertSummaryResponse)
def get_alert_summary(
    session: Session = Depends(get_session),
) -> AlertSummaryResponse:
    """Aggregate statistics for all safety alerts."""
    data = repo.get_alert_summary(session)
    return AlertSummaryResponse(**data)


# ---------------------------------------------------------------------------
# Scan
# ---------------------------------------------------------------------------

@router.post("/scan", response_model=ScanResponse)
def trigger_alert_scan(
    limit: int = Query(1000, ge=1, le=5000),
    ai: bool = Query(True, description="Classify UNCATEGORIZED domains with AI before scanning"),
    ai_limit: int = Query(20, ge=1, le=100, description="Max UNCATEGORIZED domains for the AI pass"),
    session: Session = Depends(get_session),
) -> ScanResponse:
    """Scan recent DNS queries against all safety vectors and generate alerts.

    Classifications are refreshed first (static rules, then the bounded AI
    pass) so a domain the rules don't know — e.g. a new adult site — is
    labeled *before* evaluation instead of slipping through as
    UNCATEGORIZED. The AI pass is skipped gracefully when no OpenRouter key
    is configured, and its failures never break the scan.
    """
    import logging

    from backend.app.db import classification_repo as class_repo

    logger = logging.getLogger(__name__)
    try:
        class_repo.sync_unclassified(session)
        if ai:
            ai_result = class_repo.ai_sync_uncategorized(session, limit=ai_limit)
            if ai_result.get("ai_classified"):
                logger.info(
                    "alert_scan_ai_classified count=%d still_unknown=%d",
                    ai_result["ai_classified"], ai_result.get("still_unknown", 0),
                )
    except Exception as exc:
        logger.warning("alert_scan_presync_failed error=%s", exc)
    result = repo.scan_queries_for_alerts(session, limit=limit)
    session.commit()
    return ScanResponse(**result)


# ---------------------------------------------------------------------------
# Single Alert Detail
# ---------------------------------------------------------------------------

@router.get("/{alert_id}", response_model=SafetyAlertRead)
def get_alert_detail(
    alert_id: int,
    session: Session = Depends(get_session),
) -> SafetyAlertRead:
    """Fetch details and full explainability for a specific alert."""
    alert = repo.get_alert(session, alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")
    return _read_alert(alert, _device_names(session))


# ---------------------------------------------------------------------------
# Status Update
# ---------------------------------------------------------------------------

@router.patch("/{alert_id}", response_model=SafetyAlertRead)
def update_alert(
    alert_id: int,
    body: SafetyAlertUpdate,
    request: Request,
    session: Session = Depends(get_session),
) -> SafetyAlertRead:
    """Update alert status (e.g. ACKNOWLEDGED, DISMISSED, RESOLVED)."""
    try:
        status_enum = AlertStatus(body.status.upper())
    except ValueError:
        valid = [s.value for s in AlertStatus]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{body.status}'. Valid values: {valid}",
        )

    alert = repo.update_alert_status(session, alert_id, status_enum)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")

    # Record audit log entry
    audit = AuditLog(
        timestamp=datetime.now(timezone.utc).isoformat(),
        actor_ip=get_client_ip(request),
        action="ALERT_STATUS_UPDATE",
        target=str(alert_id),
        details=json.dumps({"new_status": status_enum.value, "domain": alert.domain}),
    )
    session.add(audit)

    session.commit()
    session.refresh(alert)
    return _read_alert(alert, _device_names(session))
