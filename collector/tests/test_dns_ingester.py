"""Tests for collector.dns.ingester (Ingester class).

All tests use temporary directories and in-memory or on-disk SQLite.
No dnsmasq process is required; we simulate log file content directly.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from collector.device_discovery import storage
from collector.dns.ingester import Ingester


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_db(tmp_path: Path) -> Path:
    db = tmp_path / "test.sqlite3"
    conn = storage.init_db(db)
    conn.close()
    return db


def _seed_device(db_path: Path, ip: str, mac: str) -> str:
    """Create a device with a known IP in the database. Returns device_id."""
    conn = storage.init_db(db_path)
    try:
        device_id = storage.create_device(
            conn, primary_mac=mac, mac_is_randomized=False,
            confidence="HIGH", now_iso="2026-09-12T20:00:00+00:00",
        )
        storage.record_observation(
            conn, device_id=device_id, ip_address=ip,
            mac_address=mac, hostname=None, vendor=None,
            observed_at_iso="2026-09-12T20:00:00+00:00",
        )
        return device_id
    finally:
        conn.close()


def _log_query(domain: str, source_ip: str, qtype: str = "A") -> str:
    return f"Sep 12 21:00:01 dnsmasq[1234]: query[{qtype}] {domain} from {source_ip}\n"


def _log_reply(domain: str, answer: str) -> str:
    return f"Sep 12 21:00:01 dnsmasq[1234]: reply {domain} is {answer}\n"


# ── basic processing ───────────────────────────────────────────────────────────

class TestProcessNewLines:
    def test_processes_log_file_and_writes_to_db(self, tmp_path):
        db = _make_db(tmp_path)
        log = tmp_path / "dnsmasq.log"
        log.write_text(
            _log_query("example.com", "192.168.1.10")
            + _log_query("other.com", "192.168.1.10")  # second query flushes first
        )
        ingester = Ingester(log_path=log, db_path=db)
        count = ingester.process_new_lines()
        assert count == 1  # "other.com" is still buffered

        # flush to get the last one
        ingester.flush_and_stop()

        conn = storage.init_db(db)
        try:
            queries = storage.get_recent_dns_queries(conn, limit=10)
        finally:
            conn.close()
        domains = {q.domain for q in queries}
        assert "example.com" in domains

    def test_no_queries_processed_when_log_missing(self, tmp_path):
        db = _make_db(tmp_path)
        ingester = Ingester(log_path=tmp_path / "nonexistent.log", db_path=db)
        assert ingester.process_new_lines() == 0

    def test_position_file_prevents_double_processing(self, tmp_path):
        db = _make_db(tmp_path)
        log = tmp_path / "dnsmasq.log"
        log.write_text(
            _log_query("first.com", "192.168.1.1")
            + _log_query("flush.com", "192.168.1.1")
        )
        ingester = Ingester(log_path=log, db_path=db)
        count1 = ingester.process_new_lines()
        count2 = ingester.process_new_lines()  # same bytes — nothing new
        assert count1 == 1
        assert count2 == 0

    def test_new_lines_appended_to_log_are_picked_up(self, tmp_path):
        db = _make_db(tmp_path)
        log = tmp_path / "dnsmasq.log"
        log.write_text(_log_query("first.com", "192.168.1.1") +
                       _log_query("flush1.com", "192.168.1.1"))
        ingester = Ingester(log_path=log, db_path=db)
        count1 = ingester.process_new_lines()
        # "first.com" is emitted when "flush1.com" arrives; "flush1.com"
        # itself is left buffered (nothing after it yet).
        assert count1 == 1

        # Append new lines
        with log.open("a") as fh:
            fh.write(_log_query("second.com", "192.168.1.2") +
                     _log_query("flush2.com", "192.168.1.2"))
        count2 = ingester.process_new_lines()
        # "second.com" arrives → flushes buffered "flush1.com" (1 write)
        # "flush2.com" arrives → flushes "second.com" (1 write)
        # "flush2.com" itself is buffered.  Total: 2 writes.
        assert count2 == 2

    def test_log_rotation_resets_position(self, tmp_path):
        """If the log shrinks (rotation), the ingester resets to position 0."""
        db = _make_db(tmp_path)
        log = tmp_path / "dnsmasq.log"
        log.write_text(_log_query("before-rotation.com", "192.168.1.1") +
                       _log_query("flush.com", "192.168.1.1"))
        ingester = Ingester(log_path=log, db_path=db)
        ingester.process_new_lines()

        # Simulate log rotation: new shorter file
        log.write_text(_log_query("after-rotation.com", "192.168.1.1"))
        count = ingester.process_new_lines()
        # Nothing fully flushed yet (only one query, still buffered)
        assert count == 0
        # Confirm position was reset by flushing
        ingester.flush_and_stop()
        conn = storage.init_db(db)
        try:
            queries = storage.get_recent_dns_queries(conn, limit=20)
        finally:
            conn.close()
        domains = {q.domain for q in queries}
        assert "after-rotation.com" in domains


# ── IP → device_id join ────────────────────────────────────────────────────────

class TestDeviceIdResolution:
    def test_known_ip_is_attributed_to_device(self, tmp_path):
        db = _make_db(tmp_path)
        device_id = _seed_device(db, "192.168.1.42", "aa:bb:cc:dd:ee:ff")

        log = tmp_path / "dnsmasq.log"
        log.write_text(
            _log_query("apple.com", "192.168.1.42")
            + _log_query("flush.com", "192.168.1.42")
        )
        ingester = Ingester(log_path=log, db_path=db)
        ingester.process_new_lines()

        conn = storage.init_db(db)
        try:
            queries = storage.get_dns_queries_by_device(conn, device_id)
        finally:
            conn.close()
        assert any(q.domain == "apple.com" for q in queries)

    def test_unknown_ip_gets_partial_visibility(self, tmp_path):
        db = _make_db(tmp_path)
        log = tmp_path / "dnsmasq.log"
        # Loopback is the host talking to itself, never a LAN client, so it
        # stays PARTIAL instead of growing a placeholder device.
        log.write_text(
            _log_query("bypass.com", "127.0.0.2")
            + _log_query("flush.com", "127.0.0.2")
        )
        ingester = Ingester(log_path=log, db_path=db)
        ingester.process_new_lines()

        conn = storage.init_db(db)
        try:
            queries = storage.get_recent_dns_queries(conn, limit=10)
        finally:
            conn.close()
        bypass_query = next((q for q in queries if q.domain == "bypass.com"), None)
        assert bypass_query is not None
        assert bypass_query.dns_visibility == "PARTIAL"
        assert bypass_query.device_id is None

    def test_unknown_lan_ip_grows_placeholder_device(self, tmp_path):
        """A never-scanned LAN client must be attributed from its first
        query (the reported bug: new devices sat Unassigned for a day)."""
        db = _make_db(tmp_path)
        log = tmp_path / "dnsmasq.log"
        log.write_text(
            _log_query("newphone.com", "192.168.1.15")
            + _log_query("flush.com", "192.168.1.15")
        )
        ingester = Ingester(log_path=log, db_path=db)
        ingester.process_new_lines()

        conn = storage.init_db(db)
        try:
            queries = storage.get_recent_dns_queries(conn, limit=10)
            devices = storage.get_all_devices(conn)
        finally:
            conn.close()
        new_query = next((q for q in queries if q.domain == "newphone.com"), None)
        assert new_query is not None
        assert new_query.dns_visibility == "FULL"
        assert new_query.device_id is not None
        placeholder = next(
            (d for d in devices if d.device_id == new_query.device_id), None
        )
        assert placeholder is not None
        assert placeholder.primary_mac is None
        assert placeholder.confidence == "LOW"

    def test_public_ip_never_grows_placeholder_device(self, tmp_path):
        db = _make_db(tmp_path)
        log = tmp_path / "dnsmasq.log"
        log.write_text(
            _log_query("weird.com", "8.8.8.8")
            + _log_query("flush.com", "8.8.8.8")
        )
        ingester = Ingester(log_path=log, db_path=db)
        ingester.process_new_lines()

        conn = storage.init_db(db)
        try:
            queries = storage.get_recent_dns_queries(conn, limit=10)
            devices = storage.get_all_devices(conn)
        finally:
            conn.close()
        weird_query = next((q for q in queries if q.domain == "weird.com"), None)
        assert weird_query is not None
        assert weird_query.dns_visibility == "PARTIAL"
        assert weird_query.device_id is None
        assert devices == []

    def test_known_ip_gets_full_visibility(self, tmp_path):
        db = _make_db(tmp_path)
        device_id = _seed_device(db, "192.168.1.10", "11:22:33:44:55:66")

        log = tmp_path / "dnsmasq.log"
        log.write_text(
            _log_query("full.com", "192.168.1.10")
            + _log_query("flush.com", "192.168.1.10")
        )
        ingester = Ingester(log_path=log, db_path=db)
        ingester.process_new_lines()

        conn = storage.init_db(db)
        try:
            queries = storage.get_recent_dns_queries(conn, limit=10)
        finally:
            conn.close()
        full_query = next((q for q in queries if q.domain == "full.com"), None)
        assert full_query is not None
        assert full_query.dns_visibility == "FULL"
        assert full_query.device_id == device_id


class TestPlaceholderAdoption:
    def test_scan_enriches_placeholder_instead_of_duplicating(self, tmp_path, monkeypatch):
        """End-to-end of the reported bug: unknown IP queries create a
        placeholder; the next scan observing (same IP + MAC) must adopt the
        MAC into that same device, not create a second one."""
        from collector.device_discovery import arp_scan, discovery_service, router_clients
        from collector.device_discovery.network_info import NetworkInfo

        db = _make_db(tmp_path)
        log = tmp_path / "dnsmasq.log"
        log.write_text(
            _log_query("newphone.com", "192.168.1.15")
            + _log_query("flush.com", "192.168.1.15")
        )
        Ingester(log_path=log, db_path=db).process_new_lines()

        conn = storage.init_db(db)
        try:
            (placeholder,) = storage.get_all_devices(conn)
        finally:
            conn.close()

        monkeypatch.setattr(
            arp_scan, "discover_hosts",
            lambda *a, **k: arp_scan.DiscoveryResult(
                neighbors=[], active_scan_attempted=True,
                active_scan_succeeded=True, unavailable_reason=None,
            ),
        )
        monkeypatch.setattr(
            discovery_service.hostname_resolver, "resolve_hostname", lambda ip: None,
        )
        monkeypatch.setattr(
            router_clients, "get_router_clients",
            lambda: [router_clients.RouterClient(
                ip="192.168.1.15", mac="4c:0f:6e:95:32:12", hostname="Ahmed-PC",
            )],
        )
        network = NetworkInfo(
            interface="eth0", local_ip="192.168.1.20", subnet_cidr="192.168.1.0/24",
            gateway_ip="192.168.1.1", mac_address=None, ipv6_active=False,
            ipv6_global_addresses=(),
        )
        conn = storage.init_db(db)
        try:
            summary = discovery_service.run_discovery_cycle(
                conn, network, attempt_active=True,
            )
            devices = storage.get_all_devices(conn)
            queries = storage.get_dns_queries_by_device(conn, placeholder.device_id)
        finally:
            conn.close()

        assert summary.devices_seen == 1
        assert len(devices) == 1  # no duplicate
        assert devices[0].device_id == placeholder.device_id
        assert (devices[0].primary_mac or "").lower() == "4c:0f:6e:95:32:12"
        assert any(q.domain == "newphone.com" for q in queries)


# ── flush_and_stop ─────────────────────────────────────────────────────────────

class TestFlushAndStop:
    def test_flush_writes_last_buffered_entry(self, tmp_path):
        db = _make_db(tmp_path)
        log = tmp_path / "dnsmasq.log"
        # Only one query — never flushed by a second query arriving
        log.write_text(_log_query("last.com", "192.168.1.1"))
        ingester = Ingester(log_path=log, db_path=db)
        count = ingester.process_new_lines()
        assert count == 0  # buffered, not yet written

        flushed = ingester.flush_and_stop()
        assert flushed == 1

        conn = storage.init_db(db)
        try:
            queries = storage.get_recent_dns_queries(conn, limit=5)
        finally:
            conn.close()
        assert any(q.domain == "last.com" for q in queries)

    def test_flush_returns_zero_when_nothing_buffered(self, tmp_path):
        db = _make_db(tmp_path)
        log = tmp_path / "dnsmasq.log"
        log.write_text("")
        ingester = Ingester(log_path=log, db_path=db)
        ingester.process_new_lines()
        assert ingester.flush_and_stop() == 0
