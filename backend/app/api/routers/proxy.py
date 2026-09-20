"""Web-proxy observation API — Phase 19.

GET /api/proxy/requests — paginated proxied request metadata
GET /api/proxy/searches  — extracted search keywords per device
GET /api/proxy/ca.pem    — parental CA certificate (public cert only, for
                           installing on supervised devices)

Only devices configured to use this PC as their HTTP(S) proxy (with the
parental CA trusted) appear here. Everything else stays DNS-only.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.db.session import get_session
from backend.app.models.device import Device
from backend.app.models.dns import DnsQuery
from backend.app.models.proxy import ProxyRequest, ProxySearchTerm
from backend.app.schemas.proxy import (
    PaginatedProxyResponse,
    ProxyRequestItem,
    ProxySearchItem,
)

router = APIRouter(prefix="/proxy", tags=["Web Proxy"])

CA_DIR = Path(os.environ.get("PROXY_CA_DIR", "/opt/parental-safety/proxy/ca"))


def _local_hosts() -> set[str]:
    """Infrastructure hosts hidden by `hide_local`: the router, this PC's
    own LAN IP, and loopback. Fail-soft — worst case the filter hides
    nothing instead of breaking the query."""
    hosts = {"192.168.1.1", "localhost", "127.0.0.1", "::1"}
    try:
        import socket

        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("8.8.8.8", 80))
            local_ip = probe.getsockname()[0]
        finally:
            probe.close()
        if local_ip and not local_ip.startswith("127."):
            hosts.add(local_ip)
    except OSError:
        pass
    return hosts


def _with_device_name(session: Session, payload: dict) -> dict:
    device_id = payload.get("device_id")
    if device_id:
        name = session.scalars(
            select(Device.friendly_name).where(Device.device_id == device_id)
        ).first()
        payload["device_name"] = name or device_id
    return payload


@router.get("/requests", response_model=PaginatedProxyResponse)
def list_proxy_requests(
    device_id: Optional[str] = Query(None),
    domain: Optional[str] = Query(None, description="Substring match on host"),
    method: Optional[str] = Query(None, description="GET, POST, …"),
    hide_local: bool = Query(True, description="Hide router/self/loopback destinations"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> PaginatedProxyResponse:
    q = session.query(ProxyRequest)
    if device_id:
        q = q.filter(ProxyRequest.device_id == device_id)
    if domain:
        q = q.filter(ProxyRequest.host.ilike(f"%{domain}%"))
    if method:
        q = q.filter(ProxyRequest.method == method.upper())
    if hide_local:
        q = q.filter(~ProxyRequest.host.in_(_local_hosts()))
    total = q.count()
    rows = (
        q.order_by(desc(ProxyRequest.id)).offset(offset).limit(limit).all()
    )
    items = []
    for r in rows:
        payload = {c.key: getattr(r, c.key) for c in r.__table__.columns}
        items.append(ProxyRequestItem(**_with_device_name(session, payload)))
    return PaginatedProxyResponse(total=total, limit=limit, offset=offset, items=items)


@router.get("/searches", response_model=list[ProxySearchItem])
def list_proxy_searches(
    device_id: Optional[str] = Query(None),
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(200, ge=1, le=1000),
    session: Session = Depends(get_session),
) -> list[ProxySearchItem]:
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    q = session.query(ProxySearchTerm).filter(ProxySearchTerm.occurred_at >= cutoff)
    if device_id:
        q = q.filter(ProxySearchTerm.device_id == device_id)
    rows = q.order_by(desc(ProxySearchTerm.id)).limit(limit).all()
    items = []
    for r in rows:
        payload = {c.key: getattr(r, c.key) for c in r.__table__.columns}
        items.append(ProxySearchItem(**_with_device_name(session, payload)))
    return items


@router.get("/coverage")
def get_proxy_coverage(
    days: int = Query(7, ge=1, le=90),
    session: Session = Depends(get_session),
) -> dict:
    """Per-device supervision coverage: which devices send traffic through
    the proxy (keywords visible) vs DNS-only (domains only).

    A device with DNS activity but zero proxy rows was never enrolled —
    no configuration on earth can change that silently (see module
    docstring / docs); this endpoint makes the gap visible instead.
    """
    from datetime import datetime, timedelta, timezone

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    dns_counts = dict(
        session.query(DnsQuery.device_id, func.count(DnsQuery.id))
        .filter(DnsQuery.occurred_at >= cutoff)
        .filter(DnsQuery.device_id.isnot(None))
        .group_by(DnsQuery.device_id)
        .all()
    )
    proxy_counts = dict(
        session.query(ProxyRequest.device_id, func.count(ProxyRequest.id))
        .filter(ProxyRequest.occurred_at >= cutoff)
        .filter(ProxyRequest.device_id.isnot(None))
        .group_by(ProxyRequest.device_id)
        .all()
    )
    last_seen_rows = (
        session.query(ProxyRequest.device_id, func.max(ProxyRequest.occurred_at))
        .filter(ProxyRequest.device_id.isnot(None))
        .group_by(ProxyRequest.device_id)
        .all()
    )
    last_seen = {device_id: ts for device_id, ts in last_seen_rows}
    devices = session.query(Device.device_id, Device.friendly_name).all()
    return {
        "days": days,
        "devices": [
            {
                "device_id": device_id,
                "device_name": friendly_name or device_id,
                "dns_queries": dns_counts.get(device_id, 0),
                "proxy_requests": proxy_counts.get(device_id, 0),
                "has_proxy": proxy_counts.get(device_id, 0) > 0,
                "last_proxy_seen": last_seen.get(device_id),
            }
            for device_id, friendly_name in devices
        ],
    }


@router.get("/ca.pem")
def download_ca() -> FileResponse:
    """Serve the parental CA *certificate* (public part only, safe to
    distribute) so it can be installed on supervised devices."""
    cert = CA_DIR / "mitmproxy-ca-cert.pem"
    if not cert.is_file():
        raise HTTPException(status_code=404, detail="CA not generated yet")
    return FileResponse(
        path=str(cert),
        media_type="application/x-pem-file",
        filename="parental-safety-ca.pem",
    )
