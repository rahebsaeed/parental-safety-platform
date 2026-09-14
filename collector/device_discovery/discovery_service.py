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

from collector.device_discovery import arp_scan, hostname_resolver, identity, mac_vendor, storage
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

    for neighbor in result.neighbors:
        hostname = hostname_resolver.resolve_hostname(neighbor.ip)
        vendor_label, mac_is_randomized = _describe_vendor(neighbor.mac, oui_database)

        observation = identity.Observation(
            ip=neighbor.ip, mac=neighbor.mac, hostname=hostname
        )
        match = identity.match_device(observation, known_devices)

        if match.device_id is None:
            device_id = storage.create_device(
                conn,
                primary_mac=neighbor.mac,
                mac_is_randomized=match.mac_is_randomized,
                confidence=match.confidence.value,
                now_iso=now_iso,
            )
            logger.info(
                "device_detected device_id=%s ip=%s mac=%s confidence=%s reason=%s",
                device_id,
                neighbor.ip,
                neighbor.mac,
                match.confidence.value,
                match.reason,
            )
            # So a second neighbor later in this same pass could still
            # match against it, even though that shouldn't normally
            # happen for distinct IPs in one scan.
            known_devices.append(
                identity.KnownDevice(
                    device_id=device_id, primary_mac=neighbor.mac, last_hostname=hostname
                )
            )
        else:
            device_id = match.device_id
            logger.debug(
                "device_matched device_id=%s ip=%s confidence=%s reason=%s",
                device_id,
                neighbor.ip,
                match.confidence.value,
                match.reason,
            )

        storage.record_observation(
            conn,
            device_id=device_id,
            ip_address=neighbor.ip,
            mac_address=neighbor.mac,
            hostname=hostname,
            vendor=vendor_label,
            observed_at_iso=now_iso,
            confidence=match.confidence.value,
        )
        seen_ids.add(device_id)

    # Only an ACTIVE scan is evidence that an unresponsive device is
    # actually gone. A passive-only pass just reflects what the OS
    # happened to have cached already, and its absence proves nothing —
    # so passive-only runs must never mark anyone offline merely for
    # missing this snapshot. They still age out devices unseen for a
    # long time (STALE_OFFLINE_MINUTES) so the dashboard stops showing
    # long-gone devices as online forever.
    newly_offline: list[str] = []
    if attempt_active and result.active_scan_succeeded:
        newly_offline = storage.mark_offline_except(conn, seen_ids, now_iso)
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
