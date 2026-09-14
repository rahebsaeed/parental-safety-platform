"""Detect local network topology by parsing `ip route`/`ip addr` output.

Deliberately does not hardcode any subnet, interface name, or gateway —
see docs/architecture/phase-1-discovery.md, section 1, for why that
assumption would be wrong on this network specifically.

Parsing is kept separate from subprocess invocation so the parsing logic
can be unit-tested with fixture text, without needing to run on a machine
with a real network (see collector/tests/test_network_info.py).
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass

from collector.device_discovery.process_utils import CommandExecutionError, run_command

logger = logging.getLogger(__name__)


class NetworkDetectionError(RuntimeError):
    """Raised when network topology can't be determined from `ip` output."""


@dataclass(frozen=True)
class NetworkInfo:
    interface: str
    local_ip: str
    subnet_cidr: str          # e.g. "192.168.1.0/24"
    gateway_ip: str | None
    mac_address: str | None
    ipv6_active: bool
    ipv6_global_addresses: tuple[str, ...]


def _parse_default_route(route_output: str) -> tuple[str | None, str | None]:
    """Return (gateway_ip, interface) from `ip route show` text.

    Returns (None, None) if no default route line is present.
    """
    for line in route_output.splitlines():
        tokens = line.split()
        if not tokens or tokens[0] != "default":
            continue
        gateway = None
        interface = None
        for i, tok in enumerate(tokens):
            if tok == "via" and i + 1 < len(tokens):
                gateway = tokens[i + 1]
            elif tok == "dev" and i + 1 < len(tokens):
                interface = tokens[i + 1]
        return gateway, interface
    return None, None


def _parse_subnet_for_interface(route_output: str, interface: str) -> str | None:
    """Return the local subnet CIDR (e.g. '192.168.1.0/24') for `interface`
    from `ip route show` text, preferring a line with 'scope link'.
    """
    candidates = []
    for line in route_output.splitlines():
        tokens = line.split()
        if not tokens or "/" not in tokens[0]:
            continue
        if "dev" not in tokens:
            continue
        dev = tokens[tokens.index("dev") + 1]
        if dev != interface:
            continue
        try:
            network = ipaddress.ip_network(tokens[0], strict=False)
        except ValueError:
            continue
        candidates.append((tokens[0], "scope link" in line, network.version))
    # Prefer an IPv4 "scope link" entry (the directly-connected LAN subnet)
    for cidr, is_link_scope, version in candidates:
        if version == 4 and is_link_scope:
            return cidr
    for cidr, _, version in candidates:
        if version == 4:
            return cidr
    return None


def _parse_addr_show(addr_output: str) -> tuple[str | None, str | None, list[str]]:
    """Return (mac_address, primary_ipv4, ipv6_global_addresses) from
    `ip addr show <iface>` text.
    """
    mac_address: str | None = None
    ipv4: str | None = None
    ipv6_globals: list[str] = []

    for raw_line in addr_output.splitlines():
        line = raw_line.strip()
        if line.startswith("link/ether"):
            parts = line.split()
            if len(parts) >= 2:
                mac_address = parts[1]
        elif line.startswith("inet ") and ipv4 is None:
            # "inet 192.168.1.42/24 brd ... scope global ..."
            parts = line.split()
            if len(parts) >= 2:
                ipv4 = parts[1].split("/")[0]
        elif line.startswith("inet6 ") and "scope global" in line:
            parts = line.split()
            if len(parts) >= 2:
                ipv6_globals.append(parts[1].split("/")[0])

    return mac_address, ipv4, ipv6_globals


def detect_network_info(preferred_interface: str | None = None) -> NetworkInfo:
    """Auto-detect this machine's active LAN interface, subnet, gateway,
    and MAC. Raises NetworkDetectionError if it can't determine enough to
    proceed safely (better to fail loudly than guess).
    """
    try:
        route_output = run_command(["ip", "route", "show"])
    except CommandExecutionError as exc:
        raise NetworkDetectionError(str(exc)) from exc
    gateway_ip, detected_interface = _parse_default_route(route_output)

    interface = preferred_interface or detected_interface
    if not interface:
        raise NetworkDetectionError(
            "Could not determine the active network interface from "
            "'ip route show', and none was provided explicitly via "
            "DISCOVERY_INTERFACE. Run scripts/network_reality_check.sh "
            "and set DISCOVERY_INTERFACE in .env."
        )

    subnet_cidr = _parse_subnet_for_interface(route_output, interface)
    if not subnet_cidr:
        raise NetworkDetectionError(
            f"Could not determine the local subnet for interface "
            f"'{interface}'. Set DISCOVERY_SUBNET explicitly in .env."
        )

    try:
        addr_output = run_command(["ip", "addr", "show", interface])
    except CommandExecutionError as exc:
        raise NetworkDetectionError(str(exc)) from exc
    mac_address, local_ip, ipv6_globals = _parse_addr_show(addr_output)

    if not local_ip:
        raise NetworkDetectionError(
            f"Interface '{interface}' has no IPv4 address assigned. "
            "Is it actually connected?"
        )

    info = NetworkInfo(
        interface=interface,
        local_ip=local_ip,
        subnet_cidr=subnet_cidr,
        gateway_ip=gateway_ip,
        mac_address=mac_address,
        ipv6_active=bool(ipv6_globals),
        ipv6_global_addresses=tuple(ipv6_globals),
    )
    logger.info(
        "network_info_detected interface=%s subnet=%s gateway=%s ipv6_active=%s",
        info.interface,
        info.subnet_cidr,
        info.gateway_ip,
        info.ipv6_active,
    )
    return info
