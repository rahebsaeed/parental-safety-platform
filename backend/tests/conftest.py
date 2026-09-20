from __future__ import annotations

import sqlite3
import pytest
from pathlib import Path
from typing import Generator
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.session import get_db, get_session

_TEST_SCHEMA = """
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
    device_id TEXT NOT NULL REFERENCES devices(device_id),
    ip_address TEXT NOT NULL,
    mac_address TEXT,
    hostname TEXT,
    vendor TEXT,
    observed_at TEXT NOT NULL
);

CREATE TABLE device_status_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL REFERENCES devices(device_id),
    status TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE dns_queries (
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

CREATE TABLE audit_logs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  TEXT    NOT NULL,
    actor_ip   TEXT    NOT NULL,
    action     TEXT    NOT NULL,
    target     TEXT,
    details    TEXT
);

CREATE TABLE domain_classifications (
    domain       TEXT PRIMARY KEY,
    category     TEXT NOT NULL DEFAULT 'UNCATEGORIZED',
    rule_type    TEXT,
    pattern      TEXT,
    is_override  INTEGER NOT NULL DEFAULT 0,
    note         TEXT,
    classified_at TEXT
);

CREATE TABLE proxy_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    client_ip TEXT NOT NULL,
    device_id TEXT,
    method TEXT NOT NULL,
    scheme TEXT NOT NULL DEFAULT 'https',
    host TEXT NOT NULL,
    port INTEGER NOT NULL DEFAULT 443,
    path TEXT,
    full_url TEXT NOT NULL,
    user_agent TEXT,
    referer TEXT,
    req_content_type TEXT,
    req_size INTEGER NOT NULL DEFAULT 0,
    status_code INTEGER,
    resp_content_type TEXT,
    resp_size INTEGER NOT NULL DEFAULT 0,
    page_title TEXT,
    intercepted INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE proxy_search_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    device_id TEXT,
    engine TEXT NOT NULL,
    keywords TEXT NOT NULL,
    full_url TEXT NOT NULL
);
"""


@pytest.fixture
def test_db(tmp_path: Path) -> Generator[sqlite3.Connection, None, None]:
    db_file = tmp_path / "test_api.sqlite3"
    conn = sqlite3.connect(str(db_file), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(_TEST_SCHEMA)

    # Seed test data
    conn.execute(
        """
        INSERT INTO devices VALUES
        ('dev_01', 'Router Gateway', 'Router', '88:76:b9:c4:17:b2', 0, 'D-Link', 'online', 'HIGH', '2026-09-12 12:00:00', '2026-09-12 23:00:00'),
        ('dev_02', 'Kid Tablet', 'Android', '42:12:88:b8:32:56', 1, 'Private', 'online', 'HIGH', '2026-09-12 12:00:00', '2026-09-12 23:30:00'),
        ('dev_03', NULL, NULL, 'aa:bb:cc:dd:ee:ff', 0, 'Apple', 'offline', 'LOW', '2026-09-11 10:00:00', '2026-09-11 11:00:00');
        """
    )
    conn.execute(
        """
        INSERT INTO device_addresses (device_id, ip_address, mac_address, hostname, vendor, observed_at) VALUES
        ('dev_01', '192.168.1.1', '88:76:b9:c4:17:b2', 'router.home', 'D-Link', '2026-09-12 23:00:00'),
        ('dev_02', '192.168.1.4', '42:12:88:b8:32:56', 'tablet.local', 'Private', '2026-09-12 23:30:00'),
        ('dev_02', '192.168.1.99', '42:12:88:b8:32:56', 'tablet.local', 'Private', '2026-09-12 12:00:00');
        """
    )
    conn.execute(
        """
        INSERT INTO device_status_events (device_id, status, occurred_at) VALUES
        ('dev_02', 'online', '2026-09-12 12:00:00'),
        ('dev_03', 'offline', '2026-09-12 11:00:00');
        """
    )
    conn.execute(
        """
        INSERT INTO dns_queries (occurred_at, source_ip, device_id, domain, query_type, response_status, resolved_addresses, dns_visibility) VALUES
        ('2026-09-12 23:30:01', '192.168.1.4', 'dev_02', 'google.com', 'A', 'NOERROR', '142.250.190.46', 'FULL'),
        ('2026-09-12 23:30:02', '192.168.1.4', 'dev_02', 'youtube.com', 'A', 'NOERROR', '142.250.190.78', 'FULL'),
        ('2026-09-12 23:30:03', '192.168.1.4', 'dev_02', 'youtube.com', 'AAAA', 'NOERROR', '2a00:1450:4001::', 'FULL'),
        ('2026-09-12 23:30:04', '192.168.1.4', 'dev_02', 'badtracker.evil', 'A', 'NXDOMAIN', NULL, 'FULL'),
        ('2026-09-12 23:30:05', '192.168.1.200', NULL, 'bypassed-doh.com', 'A', 'NOERROR', '1.2.3.4', 'PARTIAL');
        """
    )
    conn.commit()

    yield conn
    conn.close()


@pytest.fixture
def client(test_db: sqlite3.Connection, tmp_path: Path) -> Generator[TestClient, None, None]:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    # Build a SQLAlchemy engine over the same file the raw sqlite3 conn uses.
    # This ensures auth router ORM writes (audit_logs) land in the same DB.
    db_path = tmp_path / "test_api.sqlite3"
    sa_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=sa_engine)

    def _override_get_db() -> Generator[sqlite3.Connection, None, None]:
        yield test_db

    def _override_get_session() -> Generator:
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_session] = _override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
