"""Router DNS control API — Phase: safe-DNS failover visibility & control.

The LAN stays protected only while the D-Link router advertises this PC's
dnsmasq (192.168.1.20) as DNS. When the PC suspends, shuts down, or loses
WiFi, the router must fall back to itself (192.168.1.1) or the whole
network loses name resolution.

GET  /api/router-dns/status — read the router's current DNS (pridns/secdns)
POST /api/router-dns/mode   — switch it via the canonical router-dns.sh script

Both endpoints talk to the router over LAN HTTP with the same login flow
as infrastructure/scripts/router-dns.sh. Failures degrade to
mode="unreachable" (status) or HTTP 502 (switch) — never a 500, and the
router password hash is never logged.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from typing import Optional

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/router-dns", tags=["Router DNS"])

DNSMASQ_IP = "192.168.1.20"
ROUTER_IP = "192.168.1.1"
_SWITCH_SCRIPT = "/opt/parental-safety/scripts/router-dns.sh"


class ModeBody(BaseModel):
    mode: str = Field(..., description='"dnsmasq" (filtered, PC on) or "router" (unfiltered fallback)')


def _router_settings() -> tuple[str, str]:
    """Return (base_url, pwd_hash) from env, defaulting to the values the
    shell automation uses, so API and scripts can never disagree."""
    base_url = os.environ.get("ROUTER_BASE_URL", f"http://{ROUTER_IP}").rstrip("/")
    pwd_hash = os.environ.get(
        "ROUTER_PWD_HASH", "ee11cbb19052e40b07aac0ca060c23ee"
    )
    user = os.environ.get("ROUTER_USER", "user")
    return base_url, user, pwd_hash


def _read_router_dns(timeout: float = 10.0) -> dict:
    """Log in and read pridns/secdns from the router's Network page."""
    base_url, user, pwd_hash = _router_settings()
    cache_buster = int(time.time() * 1000)
    session = requests.Session()
    session.headers.update(
        {"x-requested-with": "XMLHttpRequest", "accept": "*/*"}
    )
    login = session.get(
        f"{base_url}/cgi-bin/Login.asp",
        params={"User": user, "Pwd": pwd_hash, "_": cache_buster},
        timeout=timeout,
    )
    login.raise_for_status()
    page = session.get(
        f"{base_url}/cgi-bin/New_GUI/Network.asp",
        params={"_": int(time.time() * 1000)},
        timeout=timeout,
    )
    page.raise_for_status()

    def _field(name: str) -> Optional[str]:
        match = re.search(rf'"{name}"\s*:\s*"([^"]*)"', page.text)
        value = match.group(1).strip() if match else None
        return value or None

    return {"pridns": _field("pridns"), "secdns": _field("secdns")}


def _mode_for(pridns: Optional[str], secdns: Optional[str]) -> str:
    if pridns == DNSMASQ_IP and secdns == DNSMASQ_IP:
        return "dnsmasq"
    if pridns == ROUTER_IP and secdns == ROUTER_IP:
        return "router"
    if pridns or secdns:
        return "custom"
    return "unknown"


@router.get("/status")
def get_status() -> JSONResponse:
    """Current router DNS as the router itself reports it."""
    try:
        dns = _read_router_dns()
    except requests.exceptions.RequestException as exc:
        logger.warning("router_dns_status_unreachable error=%s", exc)
        return JSONResponse(content={
            "mode": "unreachable",
            "pridns": None,
            "secdns": None,
            "dnsmasq_ip": DNSMASQ_IP,
            "router_ip": ROUTER_IP,
        })
    return JSONResponse(content={
        "mode": _mode_for(dns["pridns"], dns["secdns"]),
        "pridns": dns["pridns"],
        "secdns": dns["secdns"],
        "dnsmasq_ip": DNSMASQ_IP,
        "router_ip": ROUTER_IP,
    })


@router.post("/mode")
def set_mode(body: ModeBody) -> JSONResponse:
    """Switch router DNS. Single source of truth is router-dns.sh so the
    API, boot/shutdown units, and the NM dispatcher can never diverge."""
    mode = (body.mode or "").strip().lower()
    if mode not in ("dnsmasq", "router"):
        raise HTTPException(
            status_code=422,
            detail="mode must be 'dnsmasq' or 'router'",
        )
    arg = "on" if mode == "dnsmasq" else "off"
    try:
        proc = subprocess.run(
            [_SWITCH_SCRIPT, arg],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("router_dns_switch_failed mode=%s error=%s", mode, exc)
        raise HTTPException(status_code=502, detail=f"DNS switch failed: {exc}")
    if proc.returncode != 0:
        logger.warning(
            "router_dns_switch_failed mode=%s rc=%s stderr=%s",
            mode, proc.returncode, (proc.stderr or "")[-300:],
        )
        raise HTTPException(status_code=502, detail="Router DNS switch failed")
    return get_status()
