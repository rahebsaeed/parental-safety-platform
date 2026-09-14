"""Data structures, constants, and disclaimers for Phase 7 Analytics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Mandatory Ethical Disclaimers (Sections 11 & 34 of Specification)
# ---------------------------------------------------------------------------
NETWORK_INDICATOR_DISCLAIMER = (
    "Network-derived indicator of DNS request activity. Does not represent "
    "screen time or human engagement duration. Background processes, push "
    "notifications, and telemetry generate network requests independently of user activity."
)


@dataclass
class CategoryMetric:
    category: str
    label: str
    color: str
    icon: str
    query_count: int
    distinct_domains: int
    percentage: float


@dataclass
class HourlyMetric:
    hour: int  # 0 to 23
    query_count: int


@dataclass
class DailyMetric:
    date: str  # YYYY-MM-DD
    query_count: int
    active_devices_count: int
