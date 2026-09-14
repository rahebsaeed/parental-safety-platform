"""Enums and dataclasses for the Phase 6 Safety Alert subsystem."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    CRITICAL = "CRITICAL"  # Immediate safety concern (e.g. adult content, active malware)
    HIGH = "HIGH"          # High probability risk (e.g. gambling, known phishing pattern)
    MEDIUM = "MEDIUM"      # Suspicious activity (e.g. private DNS bypass, unusual TLD)
    LOW = "LOW"            # Informational notice (e.g. newly registered or atypical service)


class AlertType(str, Enum):
    """Types of detected safety issues."""
    UNSAFE_CATEGORY = "UNSAFE_CATEGORY"      # Adult content, gambling, etc.
    PHISHING_SUSPICIOUS = "PHISHING_SUSPICIOUS"  # Typosquatting, brand impersonation, suspicious TLD
    BYPASS_ATTEMPT = "BYPASS_ATTEMPT"        # DoH / DoT or private DNS bypass probe
    ANOMALOUS_BURST = "ANOMALOUS_BURST"      # High-frequency unknown domain burst


class AlertStatus(str, Enum):
    """Lifecycle status for an alert."""
    ACTIVE = "ACTIVE"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    DISMISSED = "DISMISSED"
    RESOLVED = "RESOLVED"


@dataclass
class DetectionResult:
    """Outcome of safety evaluation on a domain / query."""
    alert_type: AlertType
    severity: AlertSeverity
    title: str
    description: str
    rule_matched: str
    explanation: str
    evidence: Optional[dict] = None
