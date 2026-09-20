"""Pydantic schemas for Safety Alerts API."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict


class SafetyAlertRead(BaseModel):
    """Full representation of a Safety Alert."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    domain: str
    alert_type: str
    severity: str
    title: str
    description: str
    rule_matched: str
    explanation: str
    status: str
    occurrence_count: int
    created_at: str
    last_seen_at: str


class SafetyAlertUpdate(BaseModel):
    """Payload to update an alert's status."""

    status: str  # ACTIVE, ACKNOWLEDGED, DISMISSED, RESOLVED


class AlertSummaryResponse(BaseModel):
    """Aggregate statistics response."""

    total_alerts: int
    active_alerts: int
    by_severity: dict[str, int]
    by_type: dict[str, int]


class ScanResponse(BaseModel):
    """Response returned after running an alert evaluation scan."""

    scanned_queries: int
    alerts_created: int
    alerts_aggregated: int
