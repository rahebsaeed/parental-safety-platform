"""Orchestrates one full Phase 1 discovery cycle: ARP scan -> hostname /
vendor enrichment -> identity matching -> persistence.

This is the only module that talks to arp_scan, hostname_resolver,
mac_vendor, identity, AND storage together — everything else in this
package is decoupled from its siblings. Keeping the orchestration in one
place makes the "what happens in what order, and why" question answerable
by reading one file.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from collector.device_discovery import arp_scan, hostname_resolver, identity, mac_vendor, router_clients, storage
from collector.device_discovery.network_info import NetworkInfo

logger = logging.getLogger(__name__)

# Passive-only scans must never mark a device offline merely for missing
# one cache snapshot — but a device unseen for longer than this still
# counts as gone. Keeps the dashboard honest between active scans.
STALE_OFFLINE_MINUTES = 120


@dataclass(frozen=True)
class ScanSummary:
    network: NetworkInfo
    active_scan_attempted: bool
    active_scan_succeeded: bool
    unavailable_reason: str | None
    devices_seen: int
    devices_newly_offline: list[str]
    devices: list[storage.DeviceRecord]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _describe_vendor(
    mac: str | None, oui_database: dict[str, str] | None
) -> tuple[str | None, bool]:
    """Return (vendor_label, mac_is_randomized). Never fabricates a vendor
    name — see mac_vendor.py docstring.
    """
    if not mac:
        return None, False
    try:
        info = mac_vendor.describe(mac, oui_database)
    except mac_vendor.InvalidMacAddressError:
        return None, False

    if info.vendor:
        return info.vendor, info.is_locally_administered
    if info.is_locally_administered:
        return "Private/randomized address", True
    return "Unknown (no OUI database loaded)", False


def run_discovery_cycle(
    conn: sqlite3.Connection,
    network: NetworkInfo,
    *,
    attempt_active: bool = True,
    oui_database: dict[str, str] | None = None,
) -> ScanSummary:
    logger.info(
        "scan_started interface=%s subnet=%s active_requested=%s",
        network.interface,
        network.subnet_cidr,
        attempt_active,
    )

    result = arp_scan.discover_hosts(
        network.interface, network.subnet_cidr, attempt_active=attempt_active
    )
    if attempt_active and not result.active_scan_succeeded:
        logger.warning(
            "scan_permission_denied reason=%s falling_back_to=passive_only",
            result.unavailable_reason,
        )

    now_iso = _now_iso()
    known_devices = storage.get_known_devices_for_matching(conn)
    seen_ids: set[str] = set()
    seen_mac_ip: set[tuple[str | None, str]] = set()

    def _ingest(ip: str, mac: str | None, hostname: str | None, source: str) -> None:
        observation = identity.Observation(ip=ip, mac=mac, hostname=hostname)
        match = identity.match_device(observation, known_devices)

        if match.device_id is None:
            device_id = storage.create_device(
                conn,
                primary_mac=mac,
                mac_is_randomized=match.mac_is_randomized,
                confidence=match.confidence.value,
                now_iso=now_iso,
            )
            logger.info(
                "device_detected device_id=%s ip=%s mac=%s confidence=%s reason=%s source=%s",
                device_id,
                ip,
                mac,
                match.confidence.value,
                match.reason,
                source,
            )
            # So a second observation later in this same pass could still
            # match against it, even though that shouldn't normally
            # happen for distinct IPs in one scan.
            known_devices.append(
                identity.KnownDevice(
                    device_id=device_id, primary_mac=mac, last_hostname=hostname
                )
            )
        else:
            device_id = match.device_id
            logger.debug(
                "device_matched device_id=%s ip=%s confidence=%s reason=%s source=%s",
                device_id,
                ip,
                match.confidence.value,
                match.reason,
                source,
            )

        vendor_label, _ = _describe_vendor(mac, oui_database)
        storage.record_observation(
            conn,
            device_id=device_id,
            ip_address=ip,
            mac_address=mac,
            hostname=hostname,
            vendor=vendor_label,
            observed_at_iso=now_iso,
            confidence=match.confidence.value,
        )
        seen_ids.add(device_id)
        seen_mac_ip.add(((mac or "").lower() or None, ip))

    for neighbor in result.neighbors:
        hostname = hostname_resolver.resolve_hostname(neighbor.ip)
        _ingest(neighbor.ip, neighbor.mac, hostname, source="arp")

    # The router's DHCP lease table sees devices ARP misses (phones in
    # power-save, hosts absent from the OS ARP cache). Merge it here so a
    # scan reflects everything the router itself reports. Best-effort twice
    # over: get_router_clients() swallows network errors into [], and this
    # guard covers any future change to that contract — a router hiccup must
    # never fail a scan.
    try:
        router_leases = router_clients.get_router_clients()
    except Exception as exc:
        logger.warning("router_clients_unavailable error=%s", exc)
        router_leases = []
    for lease in router_leases:
        key = ((lease.mac or "").lower() or None, lease.ip)
        if key in seen_mac_ip:
            continue
        hostname = lease.hostname or hostname_resolver.resolve_hostname(lease.ip)
        _ingest(lease.ip, lease.mac, hostname, source="router")

    # Only an ACTIVE scan is evidence that an unresponsive device is
    # actually gone. A passive-only pass just reflects what the OS
    # happened to have cached already, and its absence proves nothing —
    # so passive-only runs must never mark anyone offline merely for
    # missing this snapshot. They still age out devices unseen for a
    # long time (STALE_OFFLINE_MINUTES) so the dashboard stops showing
    # long-gone devices as online forever.
    newly_offline: list[str] = []
    if attempt_active and result.active_scan_succeeded:
        # A device that asked DNS questions minutes ago is present even if
        # this scan didn't observe it (quiet NIC, missed ARP) — asking is
        # proof of life. Without this, active scans flap DNS-active hosts
        # (e.g. a PC on a static IP) offline every hour.
        now_dt = datetime.now(timezone.utc)
        dns_cutoff = (now_dt - timedelta(minutes=30)).isoformat()
        dns_active = storage.get_devices_with_recent_dns(conn, dns_cutoff)
        present_ids = seen_ids | dns_active
        if dns_active - seen_ids:
            logger.info(
                "devices_kept_online_by_dns count=%d",
                len(dns_active - seen_ids),
            )
        newly_offline = storage.mark_offline_except(conn, present_ids, now_iso)
        for device_id in newly_offline:
            logger.info("device_offline device_id=%s", device_id)
    else:
        now_dt = datetime.now(timezone.utc)
        stale_cutoff = (now_dt - timedelta(minutes=STALE_OFFLINE_MINUTES)).isoformat()
        newly_offline = storage.mark_stale_offline(conn, stale_cutoff, now_iso)
        for device_id in newly_offline:
            logger.info("device_stale_offline device_id=%s", device_id)

    devices = storage.get_all_devices(conn)
    logger.info(
        "scan_completed devices_seen=%d devices_newly_offline=%d active_scan_succeeded=%s",
        len(seen_ids),
        len(newly_offline),
        result.active_scan_succeeded,
    )

    return ScanSummary(
        network=network,
        active_scan_attempted=attempt_active,
        active_scan_succeeded=result.active_scan_succeeded,
        unavailable_reason=result.unavailable_reason,
        devices_seen=len(seen_ids),
        devices_newly_offline=newly_offline,
        devices=devices,
    )
