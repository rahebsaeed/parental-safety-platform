"""Device discovery via ARP: an active broadcast scan (needs root) with a
passive neighbor-table fallback (works for anyone, sees less).

Why active ARP scanning works on encrypted Wi-Fi even though passive
sniffing of *other devices' unicast traffic* does not: ARP requests and
replies are broadcast/multicast frames, encrypted with the network's
shared Group Temporal Key rather than a per-client pairwise key, so any
legitimate member of the network can send and receive them. See
docs/architecture/phase-1-discovery.md for the full explanation.

scapy is imported lazily inside active_arp_scan() so that this module —
and its passive-parsing functions — can be imported and unit-tested
without scapy installed and without root.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from collector.device_discovery.process_utils import CommandExecutionError, run_command

logger = logging.getLogger(__name__)


class ActiveScanUnavailableError(RuntimeError):
    """Active ARP scan couldn't run: missing privileges, scapy not
    installed, or an OS-level socket error. Callers should treat this as
    'fall back to passive', not as a fatal error.
    """


@dataclass(frozen=True)
class RawNeighbor:
    ip: str
    mac: str
    interface: str | None
    source: str  # "active_arp" | "passive_neighbor_cache"


@dataclass(frozen=True)
class DiscoveryResult:
    neighbors: list[RawNeighbor]
    active_scan_attempted: bool
    active_scan_succeeded: bool
    unavailable_reason: str | None


def _parse_neighbor_lines(
    text: str, interface_filter: str | None = None
) -> list[RawNeighbor]:
    """Parse `ip neigh show` or `ip -6 neigh show` output. Works for both
    address families since the line format is the same modulo an optional
    'router' token on IPv6 lines, which this ignores.

    IPv6 link-local entries (fe80::/10) are skipped: they do not
    correspond to a routable LAN address and would confuse the
    current-IP display. Active ARP (IPv4 only) is the authoritative
    source; passive IPv6 is kept only as a fallback for devices that
    are unreachable via IPv4 — but link-local is always discarded.

    Entries with no resolved lladdr (FAILED, INCOMPLETE, or a bare IP with
    no MAC) are skipped.
    """
    results: list[RawNeighbor] = []
    for line in text.splitlines():
        tokens = line.split()
        if not tokens:
            continue
        ip = tokens[0]

        dev = None
        if "dev" in tokens:
            idx = tokens.index("dev")
            if idx + 1 < len(tokens):
                dev = tokens[idx + 1]

        if interface_filter and dev != interface_filter:
            continue

        mac = None
        if "lladdr" in tokens:
            idx = tokens.index("lladdr")
            if idx + 1 < len(tokens):
                mac = tokens[idx + 1]

        if mac is None:
            continue

        # Skip IPv6 link-local — not a routable LAN address
        if ip.startswith("fe80::") or ip.startswith("fe80%"):
            continue

        results.append(
            RawNeighbor(ip=ip, mac=mac, interface=dev, source="passive_neighbor_cache")
        )
    return results


def read_passive_neighbors(interface: str | None = None) -> list[RawNeighbor]:
    """Read both the IPv4 and IPv6 OS neighbor caches. This is a snapshot
    of what the OS already knows, not an active probe — it will miss
    devices Ubuntu hasn't exchanged any traffic with recently. See
    docs/networking/visibility-and-limitations.md.
    """
    neighbors: list[RawNeighbor] = []
    for cmd in (["ip", "neigh", "show"], ["ip", "-6", "neigh", "show"]):
        try:
            output = run_command(cmd)
        except CommandExecutionError as exc:
            logger.warning("passive_neighbor_read_failed command=%s error=%s", cmd, exc)
            continue
        neighbors.extend(_parse_neighbor_lines(output, interface_filter=interface))
    return neighbors


def active_arp_scan(
    interface: str, subnet_cidr: str, timeout: float = 3.0
) -> list[RawNeighbor]:
    """Broadcast an ARP request to every host in subnet_cidr and collect
    replies. Requires raw-socket privileges (root, or CAP_NET_RAW +
    CAP_NET_ADMIN on the interpreter). Raises ActiveScanUnavailableError
    on any failure rather than letting a raw scapy/OS exception surface —
    callers are expected to catch this specific type and fall back.
    """
    try:
        from scapy.all import ARP, Ether, srp  # noqa: PLC0415 (intentionally lazy)
    except ImportError as exc:
        raise ActiveScanUnavailableError(
            "scapy is not installed. Install it with: pip install scapy"
        ) from exc

    try:
        packet = Ether(dst="ff:ff:ff:ff:ff:ff") / ARP(pdst=subnet_cidr)
        answered, _unanswered = srp(
            packet, timeout=timeout, iface=interface, verbose=False
        )
    except PermissionError as exc:
        raise ActiveScanUnavailableError(
            "Active ARP scan requires raw-socket privileges. Run with "
            "sudo, or see collector/README.md for the CAP_NET_RAW "
            "alternative for running as a service."
        ) from exc
    except OSError as exc:
        raise ActiveScanUnavailableError(
            f"Active ARP scan failed at the OS level: {exc}. Check that "
            f"'{interface}' is the correct interface name."
        ) from exc

    results = []
    for _sent, received in answered:
        results.append(
            RawNeighbor(
                ip=received.psrc,
                mac=received.hwsrc,
                interface=interface,
                source="active_arp",
            )
        )
    return results


def discover_hosts(
    interface: str, subnet_cidr: str, attempt_active: bool = True
) -> DiscoveryResult:
    """Run the full Phase 1 discovery pass: try an active scan, always
    supplement with the passive cache, and report honestly whether the
    active scan actually ran (the CLI uses this to warn the user rather
    than silently under-deliver).
    """
    neighbors_by_ip: dict[str, RawNeighbor] = {}
    active_succeeded = False
    unavailable_reason: str | None = None

    if attempt_active:
        try:
            for neighbor in active_arp_scan(interface, subnet_cidr):
                neighbors_by_ip[neighbor.ip] = neighbor
            active_succeeded = True
        except ActiveScanUnavailableError as exc:
            unavailable_reason = str(exc)
            logger.warning("active_scan_unavailable reason=%s", exc)

    for neighbor in read_passive_neighbors(interface=interface):
        # Active-scan results are more current; don't let a stale passive
        # entry overwrite a fresh active one for the same IP.
        neighbors_by_ip.setdefault(neighbor.ip, neighbor)

    return DiscoveryResult(
        neighbors=list(neighbors_by_ip.values()),
        active_scan_attempted=attempt_active,
        active_scan_succeeded=active_succeeded,
        unavailable_reason=unavailable_reason,
    )
