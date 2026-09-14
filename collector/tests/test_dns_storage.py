"""Tests for the dns_queries table additions to storage.py (Phase 2).

All tests use an in-memory SQLite database so they are fast and isolated.
The same `init_db(":memory:")` pattern used by Phase 1's test_storage.py.
"""

from __future__ import annotations

import sqlite3

import pytest

from collector.device_discovery import storage


@pytest.fixture()
def conn() -> sqlite3.Connection:
    """Fresh in-memory database with full schema (Phase 1 + Phase 2)."""
    c = storage.init_db(":memory:")
    yield c
    c.close()


@pytest.fixture()
def conn_with_device(conn: sqlite3.Connection) -> tuple[sqlite3.Connection, str]:
    """Database pre-seeded with one device and one address observation."""
    device_id = storage.create_device(
        conn,
        primary_mac="aa:bb:cc:dd:ee:ff",
        mac_is_randomized=False,
        confidence="HIGH",
        now_iso="2026-09-12T20:00:00+00:00",
    )
    storage.record_observation(
        conn,
        device_id=device_id,
        ip_address="192.168.1.42",
        mac_address="aa:bb:cc:dd:ee:ff",
        hostname="myphone",
        vendor="Apple",
        observed_at_iso="2026-09-12T20:00:00+00:00",
    )
    return conn, device_id


# ── schema creation ────────────────────────────────────────────────────────────

class TestSchema:
    def test_dns_queries_table_exists_in_new_db(self, conn):
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert "dns_queries" in tables

    def test_dns_queries_has_required_columns(self, conn):
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(dns_queries)")}
        required = {
            "id", "occurred_at", "source_ip", "device_id",
            "domain", "query_type", "response_status",
            "resolved_addresses", "dns_visibility",
        }
        assert required <= cols

    def test_migration_adds_dns_queries_to_existing_phase1_db(self, tmp_path):
        """A database created with the old Phase 1 schema (no dns_queries table)
        gets the table added by _ensure_schema_migrations without losing any
        Phase 1 data.
        """
        db_path = tmp_path / "old.sqlite3"

        # Create an old-style DB with only Phase 1 tables
        old_schema = """
        CREATE TABLE devices (
            device_id TEXT PRIMARY KEY,
            friendly_name TEXT,
            device_type TEXT,
            primary_mac TEXT,
            mac_is_randomized INTEGER NOT NULL DEFAULT 0,
            vendor TEXT,
            status TEXT NOT NULL DEFAULT 'online',
            confidence TEXT NOT NULL DEFAULT 'LOW',
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL
        );
        CREATE TABLE device_addresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            ip_address TEXT NOT NULL,
            mac_address TEXT,
            hostname TEXT,
            vendor TEXT,
            observed_at TEXT NOT NULL
        );
        CREATE TABLE device_status_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            status TEXT NOT NULL,
            occurred_at TEXT NOT NULL
        );
        INSERT INTO devices (device_id, primary_mac, mac_is_randomized, status,
                             confidence, first_seen, last_seen)
        VALUES ('dev_01', 'aa:bb:cc:00:00:01', 0, 'online', 'HIGH',
                '2026-09-01T00:00:00+00:00', '2026-09-01T00:00:00+00:00');
        """
        raw = sqlite3.connect(str(db_path))
        raw.executescript(old_schema)
        raw.close()

        # Running init_db should apply migrations without wiping existing data
        conn = storage.init_db(db_path)
        try:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "dns_queries" in tables

            # Phase 1 data intact
            device = storage.get_device(conn, "dev_01")
            assert device is not None
            assert device.primary_mac == "aa:bb:cc:00:00:01"
        finally:
            conn.close()


# ── insert_dns_query ───────────────────────────────────────────────────────────

class TestInsertDnsQuery:
    def test_insert_returns_integer_id(self, conn):
        row_id = storage.insert_dns_query(
            conn,
            occurred_at="2026-09-12T21:00:00+00:00",
            source_ip="192.168.1.10",
            device_id=None,
            domain="example.com",
            query_type="A",
        )
        assert isinstance(row_id, int)
        assert row_id >= 1

    def test_insert_with_all_fields(self, conn_with_device):
        conn, device_id = conn_with_device
        row_id = storage.insert_dns_query(
            conn,
            occurred_at="2026-09-12T21:00:00+00:00",
            source_ip="192.168.1.42",
            device_id=device_id,
            domain="google.com",
            query_type="A",
            response_status="NOERROR",
            resolved_addresses="142.250.80.46,142.250.80.78",
            dns_visibility="FULL",
        )
        assert row_id >= 1

    def test_insert_null_device_id_allowed(self, conn):
        """NULL device_id is valid — represents an unknown IP."""
        row_id = storage.insert_dns_query(
            conn,
            occurred_at="2026-09-12T21:00:01+00:00",
            source_ip="10.0.0.99",
            device_id=None,
            domain="unknown.example.com",
            query_type="A",
            dns_visibility="PARTIAL",
        )
        assert row_id >= 1


# ── get_recent_dns_queries ─────────────────────────────────────────────────────

class TestGetRecentDnsQueries:
    def test_returns_empty_list_when_no_queries(self, conn):
        assert storage.get_recent_dns_queries(conn) == []

    def test_returns_most_recent_first(self, conn):
        storage.insert_dns_query(
            conn, occurred_at="2026-09-12T20:00:00+00:00",
            source_ip="192.168.1.1", device_id=None,
            domain="earlier.com", query_type="A",
        )
        storage.insert_dns_query(
            conn, occurred_at="2026-09-12T21:00:00+00:00",
            source_ip="192.168.1.1", device_id=None,
            domain="later.com", query_type="A",
        )
        results = storage.get_recent_dns_queries(conn, limit=10)
        assert results[0].domain == "later.com"
        assert results[1].domain == "earlier.com"

    def test_limit_is_respected(self, conn):
        for i in range(10):
            storage.insert_dns_query(
                conn, occurred_at=f"2026-09-12T21:00:{i:02d}+00:00",
                source_ip="192.168.1.1", device_id=None,
                domain=f"site{i}.com", query_type="A",
            )
        results = storage.get_recent_dns_queries(conn, limit=3)
        assert len(results) == 3

    def test_record_fields_round_trip(self, conn_with_device):
        conn, device_id = conn_with_device
        storage.insert_dns_query(
            conn,
            occurred_at="2026-09-12T21:30:00+00:00",
            source_ip="192.168.1.42",
            device_id=device_id,
            domain="apple.com",
            query_type="AAAA",
            response_status="NXDOMAIN",
            resolved_addresses=None,
            dns_visibility="FULL",
        )
        rec = storage.get_recent_dns_queries(conn, limit=1)[0]
        assert rec.domain == "apple.com"
        assert rec.query_type == "AAAA"
        assert rec.response_status == "NXDOMAIN"
        assert rec.device_id == device_id
        assert rec.dns_visibility == "FULL"


# ── get_dns_queries_by_device ──────────────────────────────────────────────────

class TestGetDnsQueriesByDevice:
    def test_filters_by_device_id(self, conn_with_device):
        conn, device_id = conn_with_device
        storage.insert_dns_query(
            conn, occurred_at="2026-09-12T21:00:00+00:00",
            source_ip="192.168.1.42", device_id=device_id,
            domain="belongs-to-device.com", query_type="A",
        )
        storage.insert_dns_query(
            conn, occurred_at="2026-09-12T21:00:01+00:00",
            source_ip="192.168.1.99", device_id=None,
            domain="different-device.com", query_type="A",
        )
        results = storage.get_dns_queries_by_device(conn, device_id)
        assert all(r.device_id == device_id for r in results)
        domains = {r.domain for r in results}
        assert "belongs-to-device.com" in domains
        assert "different-device.com" not in domains

    def test_returns_empty_for_unknown_device(self, conn):
        assert storage.get_dns_queries_by_device(conn, "dev_99") == []


# ── resolve_device_id_for_ip ───────────────────────────────────────────────────

class TestResolveDeviceIdForIp:
    def test_returns_device_id_for_known_ip(self, conn_with_device):
        conn, device_id = conn_with_device
        resolved = storage.resolve_device_id_for_ip(conn, "192.168.1.42")
        assert resolved == device_id

    def test_returns_none_for_unknown_ip(self, conn):
        assert storage.resolve_device_id_for_ip(conn, "10.99.99.99") is None

    def test_unknown_ip_in_known_subnet_is_not_attributed(self, conn_with_device):
        """Regression test: an IP never seen in device_addresses must stay
        unassigned even when the same /24 has known devices. A previous
        same-subnet fallback stamped such queries with an unrelated
        device_id (e.g. 192.168.1.5's traffic attributed to dev_07 while
        dev_07 was at 192.168.1.6)."""
        conn, device_id = conn_with_device  # owns 192.168.1.42
        assert storage.resolve_device_id_for_ip(conn, "192.168.1.99") is None

    def test_returns_most_recent_device_for_ip(self, conn):
        """If two devices ever had the same IP (e.g. DHCP re-assignment),
        we get the most recent one.
        """
        dev1 = storage.create_device(
            conn, primary_mac="aa:00:00:00:00:01", mac_is_randomized=False,
            confidence="HIGH", now_iso="2026-09-10T10:00:00+00:00",
        )
        storage.record_observation(
            conn, device_id=dev1, ip_address="192.168.1.50",
            mac_address="aa:00:00:00:00:01", hostname=None, vendor=None,
            observed_at_iso="2026-09-10T10:00:00+00:00",
        )
        dev2 = storage.create_device(
            conn, primary_mac="aa:00:00:00:00:02", mac_is_randomized=False,
            confidence="HIGH", now_iso="2026-09-12T10:00:00+00:00",
        )
        storage.record_observation(
            conn, device_id=dev2, ip_address="192.168.1.50",
            mac_address="aa:00:00:00:00:02", hostname=None, vendor=None,
            observed_at_iso="2026-09-12T10:00:00+00:00",
        )
        resolved = storage.resolve_device_id_for_ip(conn, "192.168.1.50")
        assert resolved == dev2


class TestDevicesWithRecentDns:
    def test_returns_devices_active_since_cutoff(self, conn_with_device):
        conn, device_id = conn_with_device
        storage.insert_dns_query(
            conn, occurred_at="2026-09-14T13:00:00+00:00", source_ip="192.168.1.42",
            device_id=device_id, domain="a.com", query_type="A",
        )
        assert storage.get_devices_with_recent_dns(conn, "2026-09-14T12:30:00+00:00") == {device_id}
        assert storage.get_devices_with_recent_dns(conn, "2026-09-14T13:30:00+00:00") == set()


# ── get_dns_visibility_summary ─────────────────────────────────────────────────

class TestDnsVisibilitySummary:
    def test_returns_empty_when_no_queries(self, conn):
        assert storage.get_dns_visibility_summary(conn) == []

    def test_counts_total_and_partial_queries(self, conn_with_device):
        conn, device_id = conn_with_device
        # 2 FULL queries for known device
        for i in range(2):
            storage.insert_dns_query(
                conn, occurred_at=f"2026-09-12T21:00:0{i}+00:00",
                source_ip="192.168.1.42", device_id=device_id,
                domain=f"site{i}.com", query_type="A", dns_visibility="FULL",
            )
        # 1 PARTIAL query for unknown IP
        storage.insert_dns_query(
            conn, occurred_at="2026-09-12T21:00:05+00:00",
            source_ip="10.99.99.99", device_id=None,
            domain="bypass.com", query_type="A", dns_visibility="PARTIAL",
        )
        summary = storage.get_dns_visibility_summary(conn)
        by_device = {row["device_id"]: row for row in summary}

        assert by_device[device_id]["total_queries"] == 2
        assert by_device[device_id]["partial_queries"] == 0
        assert by_device[None]["total_queries"] == 1
        assert by_device[None]["partial_queries"] == 1
