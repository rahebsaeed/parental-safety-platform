from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class DnsQueryItem(BaseModel):
    id: int
    occurred_at: str
    source_ip: str
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    domain: str
    query_type: str
    response_status: str
    resolved_addresses: Optional[str] = None
    dns_visibility: str


class PaginatedActivityResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[DnsQueryItem]
