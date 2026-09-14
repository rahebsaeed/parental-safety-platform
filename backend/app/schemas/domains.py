from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class TopDomainItem(BaseModel):
    domain: str
    query_count: int
    unique_devices: int


class DnsStatsResponse(BaseModel):
    total_queries: int
    full_visibility_queries: int
    partial_visibility_queries: int
    partial_percentage: float
    unique_domains: int
    active_devices_today: int
