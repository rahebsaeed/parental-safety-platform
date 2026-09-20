"""Pydantic schemas for Phase 7 Analytics."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict

from backend.app.analytics.types import NETWORK_INDICATOR_DISCLAIMER


class CategoryDistributionItem(BaseModel):
    category: str
    label: str
    color: str
    icon: str
    query_count: int
    distinct_domains: int
    percentage: float


class CategoryDistributionResponse(BaseModel):
    disclaimer: str = NETWORK_INDICATOR_DISCLAIMER
    device_id: Optional[str] = None
    total_queries: int
    categories: list[CategoryDistributionItem]


class HourlyActivityItem(BaseModel):
    hour: int  # 0 to 23
    query_count: int


class HourlyActivityResponse(BaseModel):
    disclaimer: str = NETWORK_INDICATOR_DISCLAIMER
    device_id: Optional[str] = None
    hourly_distribution: list[HourlyActivityItem]


class TimelineItem(BaseModel):
    date: str  # YYYY-MM-DD
    query_count: int
    active_devices_count: int


class TimelineResponse(BaseModel):
    disclaimer: str = NETWORK_INDICATOR_DISCLAIMER
    device_id: Optional[str] = None
    timeline: list[TimelineItem]


class AnalyticsOverviewResponse(BaseModel):
    disclaimer: str = NETWORK_INDICATOR_DISCLAIMER
    device_id: Optional[str] = None
    total_queries: int
    distinct_domains: int
    active_devices: int
    top_category: str


class OpenedNextItem(BaseModel):
    domain: str
    visits: int


class SearchEngineSummary(BaseModel):
    engine: str
    label: str
    visits: int
    last_seen: Optional[str] = None
    opened_next: list[OpenedNextItem] = []


class SearchEngineVisit(BaseModel):
    engine: str
    label: str
    domain: str
    occurred_at: str


class SearchEnginesResponse(BaseModel):
    disclaimer: str = NETWORK_INDICATOR_DISCLAIMER
    keywords_note: str = (
        "DNS lookups carry hostnames only — never the /search?q=... path. "
        "This view shows which search engines were used and when; "
        "the typed keywords are not visible at the DNS layer."
    )
    device_id: Optional[str] = None
    engines: list[SearchEngineSummary]
    visits: list[SearchEngineVisit]


class ExportRecordItem(BaseModel):
    id: int
    occurred_at: str
    source_ip: str
    device_id: str
    device_name: str
    domain: str
    category: str
    query_type: str
    response_status: str
    dns_visibility: str


class ExportJsonResponse(BaseModel):
    disclaimer: str = NETWORK_INDICATOR_DISCLAIMER
    record_count: int
    records: list[ExportRecordItem]
