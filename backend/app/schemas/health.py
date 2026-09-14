from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    database_connected: bool
    database_path: str
    devices_count: int
    dns_queries_count: int
    dnsmasq_running: bool
    ingester_running: bool
