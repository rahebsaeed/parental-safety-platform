"""Router DNS control API — manual-only Safe-DNS switch + 3h failsafe.

The LAN is filtered only while the router advertises this PC's dnsmasq
(192.168.1.20) as DNS. Switching is MANUAL ONLY via this API (dashboard
button) — no boot/suspend/shutdown/WiFi hook may change router DNS over
HTTP. The sole automation is a 3-hour failsafe: enabling filtered DNS
writes a deadline file, and parental-monitor-dns-revert.timer flips the
router back to itself (192.168.1.1) when the deadline passes.

GET  /api/router-dns/status — router-reported DNS + failsafe countdown
POST /api/router-dns/mode   — manual switch via the canonical router-dns.sh

Failures degrade to mode="unreachable" (status) or HTTP 502 (switch) —
never a 500, and the router password hash is never logged.
"""
from __future__ import annotations

import datetime
import logging
import os
import re
import subprocess
import time
from pathlib import Path
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

DEFAULT_MAX_HOURS = 3.0
DEFAULT_DEADLINE_FILE = "/var/lib/parental-safety/router-dns-deadline"


def _max_hours() -> float:
    """How long filtered DNS may stay on before auto-revert (hours)."""
    try:
        value = float(os.environ.get("ROUTER_DNS_MAX_HOURS", DEFAULT_MAX_HOURS))
    except ValueError:
        return DEFAULT_MAX_HOURS
    return value if value >= 0.1 else DEFAULT_MAX_HOURS


def _deadline_path() -> Path:
    return Path(os.environ.get("ROUTER_DNS_DEADLINE_FILE", DEFAULT_DEADLINE_FILE))


def _read_deadline_epoch(now: Optional[float] = None) -> Optional[int]:
    """Return the stored expiry epoch, or None if no/invalid deadline."""
    try:
        text = _deadline_path().read_text(encoding="utf-8").strip().split()[0]
        expires = int(float(text))
    except (OSError, ValueError, IndexError):
        return None
    if expires <= 0:
        return None
    return expires


def _write_deadline(expires_epoch: int) -> None:
    path = _deadline_path()
    try:
        if path.parent and str(path.parent) not in ("", "."):
            path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{expires_epoch}\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("router_dns_deadline_write_failed error=%s", exc)


def _clear_deadline() -> None:
    try:
        _deadline_path().unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("router_dns_deadline_clear_failed error=%s", exc)


def _deadline_info(now: Optional[float] = None) -> dict:
    """Countdown fields merged into every /status response."""
    now_epoch = int(now if now is not None else time.time())
    max_hours = _max_hours()
    expires = _read_deadline_epoch(now_epoch)
    if expires is None:
        return {
            "max_hours": max_hours,
            "enabled_at": None,
            "expires_at": None,
            "seconds_remaining": None,
        }
    window = int(max_hours * 3600)
    enabled = expires - window
    remaining = expires - now_epoch
    if remaining < 0:
        remaining = 0
    def _iso(epoch: int) -> str:
        return datetime.datetime.fromtimestamp(
            epoch, tz=datetime.timezone.utc
        ).isoformat()
    return {
        "max_hours": max_hours,
        "enabled_at": _iso(enabled),
        "expires_at": _iso(expires),
        "seconds_remaining": remaining,
    }


class ModeBody(BaseModel):
    mode: str = Field(..., description='"dnsmasq" (filtered, PC on) or "router" (unfiltered fallback)')


def _router_settings() -> tuple[str, str, str]:
    """Return (base_url, user, pwd_hash) from env, defaulting to the values
    the shell automation uses, so API and scripts can never disagree."""
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
    """Current router DNS as the router itself reports it, plus the
    3-hour failsafe countdown (enabled_at/expires_at/seconds_remaining)."""
    info = _deadline_info()
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
            **info,
        })
    # A stale deadline for a router that is no longer filtered is dead
    # weight — drop it so a later manual ON starts a fresh 3h window.
    if _mode_for(dns["pridns"], dns["secdns"]) != "dnsmasq" and info["expires_at"] is not None:
        _clear_deadline()
        info = _deadline_info()
    return JSONResponse(content={
        "mode": _mode_for(dns["pridns"], dns["secdns"]),
        "pridns": dns["pridns"],
        "secdns": dns["secdns"],
        "dnsmasq_ip": DNSMASQ_IP,
        "router_ip": ROUTER_IP,
        **info,
    })


@router.post("/mode")
def set_mode(body: ModeBody) -> JSONResponse:
    """Manual router-DNS switch. The ONLY writer of router DNS (no boot /
    sleep / WiFi automation exists anymore). Enabling filtered DNS starts
    the 3h failsafe deadline; falling back to the router clears it."""
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
    if mode == "dnsmasq":
        _write_deadline(int(time.time()) + int(_max_hours() * 3600))
        logger.info("router_dns_manual_on max_hours=%s", _max_hours())
    else:
        _clear_deadline()
        logger.info("router_dns_manual_off")
    return get_status()
