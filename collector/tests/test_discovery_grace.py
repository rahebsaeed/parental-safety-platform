"""Grace window for active scans: missing ONE round must not offline a device.

Observed live: a pingable, REACHABLE host missed a single broadcast ARP
sweep (WiFi power-save) and flapped offline. Devices seen within
OFFLINE_GRACE_MINUTES stay online; longer absences still go offline.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _iso_now_minus(minutes: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _seed_online(db_conn, device_id: str, last_seen_iso: str) -> None:
    db_conn.execute(
        "INSERT INTO devices (device_id, primary_mac, mac_is_randomized,"
        " status, confidence, first_seen, last_seen)"
        " VALUES (?, 'aa:bb:cc:dd:ee:ff', 0, 'online', 'HIGH', ?, ?)",
        (device_id, last_seen_iso, last_seen_iso),
    )
    db_conn.commit()


def _run_cycle(monkeypatch, db_conn):
    from collector.device_discovery import arp_scan, discovery_service, router_clients
    from collector.device_discovery.network_info import NetworkInfo

    monkeypatch.setattr(
        arp_scan,
        "discover_hosts",
        lambda *a, **k: arp_scan.DiscoveryResult(
            neighbors=[
                arp_scan.RawNeighbor(
                    ip="192.168.1.50", mac="11:22:33:44:55:66",
                    interface="eth0", source="active_arp",
                )
            ],
            active_scan_attempted=True,
            active_scan_succeeded=True,
            unavailable_reason=None,
        ),
    )
    monkeypatch.setattr(
        discovery_service.hostname_resolver, "resolve_hostname", lambda ip: None
    )
    monkeypatch.setattr(router_clients, "get_router_clients", lambda: [])
    network = NetworkInfo(
        interface="eth0", local_ip="192.168.1.20",
        subnet_cidr="192.168.1.0/24", gateway_ip="192.168.1.1",
        mac_address=None, ipv6_active=False, ipv6_global_addresses=(),
    )
    return discovery_service.run_discovery_cycle(db_conn, network, attempt_active=True)


def _status(db_conn, device_id: str) -> str:
    row = db_conn.execute(
        "SELECT status FROM devices WHERE device_id = ?", (device_id,)
    ).fetchone()
    return row["status"]


def test_missed_single_round_stays_online(monkeypatch, db_conn):
    """Seen 30 min ago (inside grace), missed this sweep → stays online."""
    _seed_online(db_conn, "dev_01", _iso_now_minus(30))
    _run_cycle(monkeypatch, db_conn)
    assert _status(db_conn, "dev_01") == "online"


def test_long_absence_goes_offline(monkeypatch, db_conn):
    """Unseen for 3h (past grace), missed this sweep → offline."""
    _seed_online(db_conn, "dev_02", _iso_now_minus(180))
    summary = _run_cycle(monkeypatch, db_conn)
    assert _status(db_conn, "dev_02") == "offline"
    assert "dev_02" in summary.devices_newly_offline
