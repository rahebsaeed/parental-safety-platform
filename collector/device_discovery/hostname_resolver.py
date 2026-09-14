"""Best-effort hostname resolution for a discovered IP.

Two strategies, tried in order:
  1. Reverse DNS (works when the router runs a LAN-scoped DNS zone tied to
     DHCP leases — most home routers don't, except for their own address,
     which systemd-resolved often synthesizes as "_gateway").
  2. mDNS/Bonjour reverse lookup via `avahi-resolve`, for devices that
     advertise themselves over the local link — common on Apple devices,
     many Android phones, printers, Chromecasts, and smart speakers.
     `avahi-utils` is optional; if it isn't installed, this strategy
     silently contributes nothing rather than erroring.

Both are best-effort. Neither is guaranteed, and that's expected —
identifying which physical device a dev_XX record corresponds to may
still require checking the device's own Wi-Fi settings, or the router's
own client list, which usually knows names Ubuntu can't see from outside.
See docs/architecture/phase-1-discovery.md.
"""

from __future__ import annotations

import logging
import socket
import subprocess

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 1.0


def reverse_dns_lookup(ip: str, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> str | None:
    """Return a hostname for `ip` via reverse DNS, or None if it can't be
    resolved (which is the common case on most home networks). Never
    raises for the "no PTR record" case — that's normal, not an error.
    """
    previous_timeout = socket.getdefaulttimeout()
    try:
        socket.setdefaulttimeout(timeout)
        hostname, _aliases, _addrs = socket.gethostbyaddr(ip)
        return hostname
    except (socket.herror, socket.gaierror, socket.timeout, OSError) as exc:
        logger.debug("reverse_dns_lookup_failed ip=%s reason=%s", ip, exc)
        return None
    finally:
        socket.setdefaulttimeout(previous_timeout)


def mdns_reverse_lookup(ip: str, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> str | None:
    """Return a hostname for `ip` via mDNS (`avahi-resolve -a <ip>`), or
    None if avahi-utils isn't installed, the call times out, or the
    address just isn't mDNS-resolvable — all three are ordinary outcomes,
    not errors, and are handled identically on purpose.
    """
    try:
        result = subprocess.run(
            ["avahi-resolve", "-a", ip],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        logger.debug("mdns_lookup_unavailable reason=avahi-resolve_not_installed")
        return None
    except subprocess.TimeoutExpired:
        logger.debug("mdns_lookup_timed_out ip=%s", ip)
        return None

    if result.returncode != 0 or not result.stdout.strip():
        return None

    # Expected success output: "<ip>\t<hostname>.local"
    parts = result.stdout.strip().split(None, 1)
    if len(parts) != 2:
        return None
    return parts[1].strip()


def resolve_hostname(ip: str) -> str | None:
    """Try reverse DNS, then fall back to mDNS. Returns None if neither
    strategy resolves anything — a very normal outcome for most devices on
    most home networks, not a sign anything is broken.
    """
    hostname = reverse_dns_lookup(ip)
    if hostname:
        return hostname

    hostname = mdns_reverse_lookup(ip)
    if hostname:
        logger.debug("hostname_resolved_via_mdns ip=%s hostname=%s", ip, hostname)
        return hostname

    return None
