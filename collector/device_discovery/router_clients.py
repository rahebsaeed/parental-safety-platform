"""Read the D-Link router's DHCP lease table as a second discovery source.

ARP-only discovery misses devices that don't answer ARP or aren't in the
OS ARP cache yet (common with phones in power-save). The router's
``home_getclientList.asp`` page already lists every active DHCP lease with
IP, MAC, and hostname — the same page you can open in a browser after
logging in — so each discovery cycle merges those leases with the ARP
neighbors before matching/persisting.

All network access is read-only HTTP against the LAN gateway. Any failure
(login rejected, router unreachable, unexpected page format) returns an
empty list so the caller can fall back to ARP-only results instead of
failing the whole scan. Secrets are never logged.
"""

from __future__ import annotations

import html
import logging
import os
import re
import time
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)

DEFAULT_ROUTER_BASE_URL = "http://192.168.1.1"
DEFAULT_ROUTER_USER = "user"
# MD5 of the router admin password, matching infrastructure/scripts/router-dns.sh.
# Overridable via ROUTER_PWD_HASH so the secret doesn't have to live here.
DEFAULT_ROUTER_PWD_HASH = "ee11cbb19052e40b07aac0ca060c23ee"

_CLIENT_VAR_RE = re.compile(r"var\s+dhcpClient(\d+)_(\w+)='([^']*)';")


@dataclass(frozen=True)
class RouterClient:
    """One DHCP lease reported by the router."""

    ip: str
    mac: str | None
    hostname: str | None


def parse_client_list_page(text: str) -> list[RouterClient]:
    """Parse the ``home_getclientList.asp`` body into lease records.

    Pure function (no network) so it can be unit-tested. Rows without both
    an IP and a MAC are skipped, as are rows the router explicitly marks
    inactive (``active='0'``) — those are stale leases, not connected
    devices. Hostnames are HTML-entity decoded (``HONOR&#45;X8a``).
    """
    fields: dict[str, dict[str, str]] = {}
    for index, name, value in _CLIENT_VAR_RE.findall(text or ""):
        fields.setdefault(index, {})[name] = value

    clients: list[RouterClient] = []
    for index in sorted(fields, key=int):
        row = fields[index]
        ip = row.get("ip", "").strip()
        mac = row.get("mac", "").strip() or None
        if not ip or not mac:
            continue
        if row.get("active", "").strip() == "0":
            continue
        raw_hostname = row.get("hostname", "").strip()
        hostname = html.unescape(raw_hostname) or None
        clients.append(RouterClient(ip=ip, mac=mac, hostname=hostname))
    return clients


def fetch_router_clients(
    base_url: str = DEFAULT_ROUTER_BASE_URL,
    user: str = DEFAULT_ROUTER_USER,
    pwd_hash: str = DEFAULT_ROUTER_PWD_HASH,
    timeout: float = 10.0,
) -> list[RouterClient]:
    """Log in to the router and return its active DHCP leases.

    Raises on network/auth errors — callers that must not fail the scan
    should catch exceptions and treat them as "no router data".
    """
    base = base_url.rstrip("/")
    cache_buster = int(time.time() * 1000)
    session = requests.Session()
    session.headers.update(
        {"x-requested-with": "XMLHttpRequest", "accept": "*/*"}
    )
    login_resp = session.get(
        f"{base}/cgi-bin/Login.asp",
        params={"User": user, "Pwd": pwd_hash, "_": cache_buster},
        timeout=timeout,
    )
    login_resp.raise_for_status()

    list_resp = session.get(
        f"{base}/cgi-bin/get/New_GUI/home_getclientList.asp",
        params={"_": int(time.time() * 1000)},
        timeout=timeout,
    )
    list_resp.raise_for_status()
    return parse_client_list_page(list_resp.text)


def get_router_clients() -> list[RouterClient]:
    """Best-effort router lease fetch using env-overridable credentials.

    Returns [] on any failure (and logs at warning, never including the
    password hash) so discovery degrades to ARP-only instead of failing.
    """
    try:
        clients = fetch_router_clients(
            base_url=os.environ.get("ROUTER_BASE_URL", DEFAULT_ROUTER_BASE_URL),
            user=os.environ.get("ROUTER_USER", DEFAULT_ROUTER_USER),
            pwd_hash=os.environ.get("ROUTER_PWD_HASH", DEFAULT_ROUTER_PWD_HASH),
        )
    except requests.exceptions.RequestException as exc:
        logger.warning("router_client_fetch_failed error=%s", exc)
        return []
    except Exception as exc:  # defensive: parsing must never break a scan
        logger.warning("router_client_parse_failed error=%s", exc)
        return []
    logger.info("router_clients_seen count=%d", len(clients))
    return clients
