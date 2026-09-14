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
        log.write_text(
            _log_query("bypass.com", "10.99.99.99")  # never seen by Phase 1
            + _log_query("flush.com", "10.99.99.99")
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
