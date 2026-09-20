"""Pydantic schemas for Phase 19 web-proxy observations."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict


class ProxyRequestItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: str
    client_ip: str
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    method: str
    scheme: str
    host: str
    port: int
    path: Optional[str] = None
    full_url: str
    user_agent: Optional[str] = None
    referer: Optional[str] = None
    req_content_type: Optional[str] = None
    req_size: int = 0
    status_code: Optional[int] = None
    resp_content_type: Optional[str] = None
    resp_size: int = 0
    page_title: Optional[str] = None


class PaginatedProxyResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[ProxyRequestItem]


class ProxySearchItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    occurred_at: str
    device_id: Optional[str] = None
    device_name: Optional[str] = None
    engine: str
    keywords: str
    full_url: str
