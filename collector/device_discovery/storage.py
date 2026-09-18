"""SQLite persistence for Phase 1 (device discovery) and Phase 2 (DNS
observation).

Schema is deliberately shaped to map onto the normalized `devices` /
`device_addresses` / `device_status_events` / `dns_queries` tables from
the original Section 16 schema, so Phase 4 (full database architecture,
Postgres) can extend or migrate this data instead of starting from nothing.

All timestamps are passed in as ISO-8601 UTC strings by the caller
(discovery_service.py / dns/ingester.py), rather than generated here with
`datetime.now()` — that keeps this module deterministic and easy to test
with fixed timestamps (see collector/tests/test_storage.py,
collector/tests/test_dns_storage.py).

All queries are parameterized. There is no network-facing input yet in
Phase 1/2, but the discipline starts here rather than being retrofitted
when Phase 3 exposes this data over an API.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from collector.device_discovery.identity import KnownDevice

_SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
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

CREATE TABLE IF NOT EXISTS device_addresses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES devices(device_id),
    ip_address TEXT NOT NULL,
    mac_address TEXT,
    hostname TEXT,
    vendor TEXT,
    observed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_device_addresses_device_id ON device_addresses(device_id);
CREATE INDEX IF NOT EXISTS idx_device_addresses_observed_at ON device_addresses(observed_at);

CREATE TABLE IF NOT EXISTS device_status_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES devices(device_id),
    status TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_status_events_device_id ON device_status_events(device_id);

-- Phase 2: DNS query log
-- Every query seen by the dnsmasq resolver is stored here.  source_ip is
-- the raw requester IP; device_id is resolved by the ingester via a JOIN
-- against device_addresses, or NULL when the IP is unknown (DoH/DoT bypass
-- or a device the Phase 1 scan hasn't seen yet).
-- dns_visibility = 'PARTIAL' when we cannot attribute the query to a known
-- device (per Section 31 of the original spec).
CREATE TABLE IF NOT EXISTS dns_queries (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at        TEXT    NOT NULL,
    source_ip          TEXT    NOT NULL,
    device_id          TEXT    REFERENCES devices(device_id),
    domain             TEXT    NOT NULL,
    query_type         TEXT    NOT NULL,
    response_status    TEXT    NOT NULL DEFAULT 'NOERROR',
    resolved_addresses TEXT,
    dns_visibility     TEXT    NOT NULL DEFAULT 'FULL'
);
CREATE INDEX IF NOT EXISTS idx_dns_device_id   ON dns_queries(device_id);
CREATE INDEX IF NOT EXISTS idx_dns_occurred_at ON dns_queries(occurred_at);
CREATE INDEX IF NOT EXISTS idx_dns_domain      ON dns_queries(domain);
"""

_DEVICE_ID_RE = re.compile(r"^dev_(\d+)$")


@dataclass(frozen=True)
class DeviceRecord:
    device_id: str
    friendly_name: str | None
    device_type: str | None
    primary_mac: str | None
    mac_is_randomized: bool
    vendor: str | None
    status: str
    confidence: str
    first_seen: str
    last_seen: str


@dataclass(frozen=True)
class AddressObservation:
    ip_address: str
    mac_address: str | None
    hostname: str | None
    vendor: str | None
    observed_at: str


def _ensure_schema_migrations(conn: sqlite3.Connection) -> None:
    """Lightweight in-place schema evolution for pre-Alembic Phase 1/2.

    `CREATE TABLE IF NOT EXISTS` is a no-op against a database that
    already exists with an older schema, so a new column or table added
    here in code would silently never appear for anyone with existing data
    — exactly the kind of thing that only shows up once someone has real,
    valuable history they can't just delete and recreate. Phase 4 (real
    database architecture) replaces this with actual Alembic migrations;
    until then, this keeps that promise for every schema change made
    incrementally during Phase 1 and 2.
    """
    # Phase 1: vendor column on devices
    existing_columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(devices)").fetchall()
    }
    if "vendor" not in existing_columns:
        conn.execute("ALTER TABLE devices ADD COLUMN vendor TEXT")
        conn.commit()

    # Phase 2: dns_queries table — CREATE TABLE IF NOT EXISTS in _SCHEMA
    # handles new databases; this handles the case where an existing database
    # was created before Phase 2 was added.
    existing_tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "dns_queries" not in existing_tables:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS dns_queries (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at        TEXT    NOT NULL,
                source_ip          TEXT    NOT NULL,
                device_id          TEXT    REFERENCES devices(device_id),
                domain             TEXT    NOT NULL,
                query_type         TEXT    NOT NULL,
                response_status    TEXT    NOT NULL DEFAULT 'NOERROR',
                resolved_addresses TEXT,
                dns_visibility     TEXT    NOT NULL DEFAULT 'FULL'
            );
            CREATE INDEX IF NOT EXISTS idx_dns_device_id   ON dns_queries(device_id);
            CREATE INDEX IF NOT EXISTS idx_dns_occurred_at ON dns_queries(occurred_at);
            CREATE INDEX IF NOT EXISTS idx_dns_domain      ON dns_queries(domain);
        """)
        conn.commit()


def init_db(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    conn.commit()
    _ensure_schema_migrations(conn)
    return conn


def _row_to_device(row: sqlite3.Row) -> DeviceRecord:
    return DeviceRecord(
        device_id=row["device_id"],
        friendly_name=row["friendly_name"],
        device_type=row["device_type"],
        primary_mac=row["primary_mac"],
        mac_is_randomized=bool(row["mac_is_randomized"]),
        vendor=row["vendor"],
        status=row["status"],
        confidence=row["confidence"],
        first_seen=row["first_seen"],
        last_seen=row["last_seen"],
    )


def get_all_devices(conn: sqlite3.Connection) -> list[DeviceRecord]:
    rows = conn.execute("SELECT * FROM devices ORDER BY device_id").fetchall()
    return [_row_to_device(r) for r in rows]


def get_device(conn: sqlite3.Connection, device_id: str) -> DeviceRecord | None:
    row = conn.execute(
        "SELECT * FROM devices WHERE device_id = ?", (device_id,)
    ).fetchone()
    return _row_to_device(row) if row else None


def _last_hostname(conn: sqlite3.Connection, device_id: str) -> str | None:
    row = conn.execute(
        "SELECT hostname FROM device_addresses "
        "WHERE device_id = ? AND hostname IS NOT NULL "
        "ORDER BY observed_at DESC LIMIT 1",
        (device_id,),
    ).fetchone()
    return row["hostname"] if row else None


def _last_ip(conn: sqlite3.Connection, device_id: str) -> str | None:
    row = conn.execute(
        "SELECT ip_address FROM device_addresses "
        "WHERE device_id = ? AND ip_address IS NOT NULL "
        "ORDER BY observed_at DESC LIMIT 1",
        (device_id,),
    ).fetchone()
    return row["ip_address"] if row else None


def get_known_devices_for_matching(conn: sqlite3.Connection) -> list[KnownDevice]:
    """Build the minimal view identity.match_device() needs, for every
    stored device (online or offline — an offline device can still come
    back and should still match by MAC).
    """
    rows = conn.execute("SELECT device_id, primary_mac FROM devices").fetchall()
    return [
        KnownDevice(
            device_id=row["device_id"],
            primary_mac=row["primary_mac"],
            last_hostname=_last_hostname(conn, row["device_id"]),
            last_ip=_last_ip(conn, row["device_id"]),
        )
        for row in rows
    ]


def get_devices_with_recent_dns(conn: sqlite3.Connection, since_iso: str) -> set[str]:
    """Device IDs with at least one DNS query at or after `since_iso`.

    A query is proof of life: discovery treats these devices as present
    even when a scan didn't observe them (quiet NIC, missed ARP), so an
    active scan never marks a chatting device offline.
    """
    rows = conn.execute(
        "SELECT DISTINCT device_id FROM dns_queries "
        "WHERE device_id IS NOT NULL AND occurred_at >= ?",
        (since_iso,),
    ).fetchall()
    return {row["device_id"] for row in rows}


def get_devices_seen_since(conn: sqlite3.Connection, since_iso: str) -> set[str]:
    """Device IDs whose last_seen is at or after `since_iso`.

    Used as a flap guard: a device that answered a recent scan but missed
    this one (WiFi power-save can drop a single broadcast ARP round) is
    still treated as present. Only devices unseen for longer than the
    grace window go offline.
    """
    rows = conn.execute(
        "SELECT device_id FROM devices WHERE last_seen >= ?",
        (since_iso,),
    ).fetchall()
    return {row["device_id"] for row in rows}


def _next_device_id(conn: sqlite3.Connection) -> str:
    rows = conn.execute("SELECT device_id FROM devices").fetchall()
    highest = 0
    for row in rows:
        match = _DEVICE_ID_RE.match(row["device_id"])
        if match:
            highest = max(highest, int(match.group(1)))
    return f"dev_{highest + 1:02d}"


def create_device(
    conn: sqlite3.Connection,
    *,
    primary_mac: str | None,
    mac_is_randomized: bool,
    confidence: str,
    now_iso: str,
) -> str:
    device_id = _next_device_id(conn)
    conn.execute(
        "INSERT INTO devices "
        "(device_id, primary_mac, mac_is_randomized, status, confidence, first_seen, last_seen) "
        "VALUES (?, ?, ?, 'online', ?, ?, ?)",
        (device_id, primary_mac, int(mac_is_randomized), confidence, now_iso, now_iso),
    )
    conn.commit()
    return device_id


def record_observation(
    conn: sqlite3.Connection,
    *,
    device_id: str,
    ip_address: str,
    mac_address: str | None,
    hostname: str | None,
    vendor: str | None,
    observed_at_iso: str,
    confidence: str | None = None,
) -> None:
    """Append an address-history row and update the device's rollup
    fields (last_seen, status, primary_mac if newly known, confidence).
    Logs an 'online' status event if the device was previously offline.
    """
    current = conn.execute(
        "SELECT status FROM devices WHERE device_id = ?", (device_id,)
    ).fetchone()
    was_offline = current is not None and current["status"] == "offline"

    conn.execute(
        "INSERT INTO device_addresses "
        "(device_id, ip_address, mac_address, hostname, vendor, observed_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (device_id, ip_address, mac_address, hostname, vendor, observed_at_iso),
    )

    set_clauses = ["last_seen = ?", "status = 'online'"]
    params: list[str] = [observed_at_iso]
    if mac_address:
        set_clauses.append("primary_mac = ?")
        params.append(mac_address)
    if vendor:
        set_clauses.append("vendor = ?")
        params.append(vendor)
    if confidence:
        set_clauses.append("confidence = ?")
        params.append(confidence)
    params.append(device_id)
    conn.execute(
        f"UPDATE devices SET {', '.join(set_clauses)} WHERE device_id = ?", params
    )

    if was_offline:
        conn.execute(
            "INSERT INTO device_status_events (device_id, status, occurred_at) "
            "VALUES (?, 'online', ?)",
            (device_id, observed_at_iso),
        )
    conn.commit()


def mark_offline_except(
    conn: sqlite3.Connection, seen_device_ids: set[str], occurred_at_iso: str
) -> list[str]:
    """Mark every currently-online device NOT in seen_device_ids as
    offline, logging a status event for each. Returns the list of
    device_ids that just transitioned.
    """
    rows = conn.execute(
        "SELECT device_id FROM devices WHERE status = 'online'"
    ).fetchall()
    newly_offline = [r["device_id"] for r in rows if r["device_id"] not in seen_device_ids]

    for device_id in newly_offline:
        conn.execute(
            "UPDATE devices SET status = 'offline' WHERE device_id = ?", (device_id,)
        )
        conn.execute(
            "INSERT INTO device_status_events (device_id, status, occurred_at) "
            "VALUES (?, 'offline', ?)",
            (device_id, occurred_at_iso),
        )
    conn.commit()
    return newly_offline


def mark_stale_offline(
    conn: sqlite3.Connection, older_than_iso: str, occurred_at_iso: str
) -> list[str]:
    """Mark online devices whose last_seen is older than older_than_iso as
    offline. Used after passive-only scans (which must never mark a device
    offline merely for being absent from one cache snapshot) so that
    long-gone devices still age out instead of showing 'online' forever.
    """
    rows = conn.execute(
        "SELECT device_id FROM devices WHERE status = 'online' AND last_seen < ?",
        (older_than_iso,),
    ).fetchall()
    newly_offline = [r["device_id"] for r in rows]
    for device_id in newly_offline:
        conn.execute(
            "UPDATE devices SET status = 'offline' WHERE device_id = ?", (device_id,)
        )
        conn.execute(
            "INSERT INTO device_status_events (device_id, status, occurred_at) "
            "VALUES (?, 'offline', ?)",
            (device_id, occurred_at_iso),
        )
    conn.commit()
    return newly_offline


def set_friendly_name(conn: sqlite3.Connection, device_id: str, name: str) -> bool:
    cursor = conn.execute(
        "UPDATE devices SET friendly_name = ? WHERE device_id = ?", (name, device_id)
    )
    conn.commit()
    return cursor.rowcount > 0


def set_device_type(conn: sqlite3.Connection, device_id: str, device_type: str) -> bool:
    cursor = conn.execute(
        "UPDATE devices SET device_type = ? WHERE device_id = ?",
        (device_type, device_id),
    )
    conn.commit()
    return cursor.rowcount > 0


def get_ip_history(
    conn: sqlite3.Connection, device_id: str, limit: int = 50
) -> list[AddressObservation]:
    rows = conn.execute(
        "SELECT ip_address, mac_address, hostname, vendor, observed_at "
        "FROM device_addresses WHERE device_id = ? "
        "ORDER BY observed_at DESC LIMIT ?",
        (device_id, limit),
    ).fetchall()
    return [AddressObservation(**dict(row)) for row in rows]


# ── Phase 2 DNS query storage ─────────────────────────────────────────────────


@dataclass(frozen=True)
class DnsQueryRecord:
    id: int
    occurred_at: str
    source_ip: str
    device_id: str | None
    domain: str
    query_type: str
    response_status: str
    resolved_addresses: str | None
    dns_visibility: str


def insert_dns_query(
    conn: sqlite3.Connection,
    *,
    occurred_at: str,
    source_ip: str,
    device_id: str | None,
    domain: str,
    query_type: str,
    response_status: str = "NOERROR",
    resolved_addresses: str | None = None,
    dns_visibility: str = "FULL",
) -> int:
    """Insert one DNS query record. Returns the new row id."""
    cursor = conn.execute(
        "INSERT INTO dns_queries "
        "(occurred_at, source_ip, device_id, domain, query_type, "
        " response_status, resolved_addresses, dns_visibility) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            occurred_at,
            source_ip,
            device_id,
            domain,
            query_type,
            response_status,
            resolved_addresses,
            dns_visibility,
        ),
    )
    conn.commit()
    return cursor.lastrowid  # type: ignore[return-value]


def _row_to_dns_query(row: sqlite3.Row) -> DnsQueryRecord:
    return DnsQueryRecord(
        id=row["id"],
        occurred_at=row["occurred_at"],
        source_ip=row["source_ip"],
        device_id=row["device_id"],
        domain=row["domain"],
        query_type=row["query_type"],
        response_status=row["response_status"],
        resolved_addresses=row["resolved_addresses"],
        dns_visibility=row["dns_visibility"],
    )


def get_recent_dns_queries(
    conn: sqlite3.Connection, limit: int = 50
) -> list[DnsQueryRecord]:
    """Return the most recent DNS queries across all devices."""
    rows = conn.execute(
        "SELECT * FROM dns_queries ORDER BY occurred_at DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [_row_to_dns_query(r) for r in rows]


def get_dns_queries_by_device(
    conn: sqlite3.Connection, device_id: str, limit: int = 50
) -> list[DnsQueryRecord]:
    """Return the most recent DNS queries for a specific device."""
    rows = conn.execute(
        "SELECT * FROM dns_queries WHERE device_id = ? "
        "ORDER BY occurred_at DESC, id DESC LIMIT ?",
        (device_id, limit),
    ).fetchall()
    return [_row_to_dns_query(r) for r in rows]


def resolve_device_id_for_ip(
    conn: sqlite3.Connection, source_ip: str
) -> str | None:
    """Look up the most recent device_id for a given source IP address by
    joining against Phase 1's device_addresses history. Returns None when
    the IP has never been seen — this is the DoH/DoT bypass signal (stored
    as dns_visibility='PARTIAL' / "Unassigned").

    Deliberately exact-match only: a previous same-subnet fallback attributed
    unknown IPs to whatever device was observed most recently, spraying one
    device's queries across unrelated devices (e.g. 192.168.1.5's traffic
    stamped dev_07 while dev_07 was at 192.168.1.6). A wrong device is worse
    than an honest unknown — hourly discovery scans keep the mapping fresh
    so the unknown window stays small.
    """
    row = conn.execute(
        "SELECT device_id FROM device_addresses "
        "WHERE ip_address = ? ORDER BY observed_at DESC LIMIT 1",
        (source_ip,),
    ).fetchone()
    if row:
        return row[0]
    return None


def get_dns_visibility_summary(
    conn: sqlite3.Connection,
) -> list[dict]:
    """Per-device DNS visibility summary — how many queries each device
    made and whether any fell through as PARTIAL (DoH/DoT bypass).
    """
    rows = conn.execute(
        """
        SELECT
            device_id,
            COUNT(*) AS total_queries,
            SUM(CASE WHEN dns_visibility = 'PARTIAL' THEN 1 ELSE 0 END) AS partial_queries
        FROM dns_queries
        GROUP BY device_id
        ORDER BY total_queries DESC
        """
    ).fetchall()
    return [dict(r) for r in rows]
