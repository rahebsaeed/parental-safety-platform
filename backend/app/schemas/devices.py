from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class DeviceAddressItem(BaseModel):
    id: int
    ip_address: str
    mac_address: Optional[str] = None
    hostname: Optional[str] = None
    vendor: Optional[str] = None
    observed_at: str


class DeviceStatusEventItem(BaseModel):
    id: int
    status: str
    occurred_at: str


class DeviceSummary(BaseModel):
    device_id: str
    friendly_name: Optional[str] = None
    device_type: Optional[str] = None
    primary_mac: Optional[str] = None
    mac_is_randomized: bool = False
    vendor: Optional[str] = None
    status: str
    confidence: str
    first_seen: str
    last_seen: str
    current_ip: Optional[str] = None
    query_count: int = 0
    dns_visibility: str = "FULL"  # "FULL", "PARTIAL", or "NONE"
    is_gateway: bool = False  # True when current_ip is the LAN default gateway (the router itself)


class DeviceDetail(DeviceSummary):
    addresses: list[DeviceAddressItem] = Field(default_factory=list)
    status_events: list[DeviceStatusEventItem] = Field(default_factory=list)
    recent_domains: list[str] = Field(default_factory=list)


class DeviceUpdate(BaseModel):
    friendly_name: Optional[str] = Field(None, max_length=100)
    device_type: Optional[str] = Field(None, max_length=50)
