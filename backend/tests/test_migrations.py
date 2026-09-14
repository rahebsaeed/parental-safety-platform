from __future__ import annotations

import sqlite3
from pathlib import Path
from backend.app.db.migrations import run_upgrade_head, run_downgrade


def test_migration_upgrade_and_downgrade(tmp_path: Path) -> None:
    db_file = tmp_path / "migration_test.sqlite3"
    db_url = f"sqlite:///{db_file}"

    # 1. Run upgrade to head
    run_upgrade_head(db_url)

    # 2. Inspect database schema with sqlite3
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {r[0] for r in cur.fetchall()}

    assert "devices" in tables
    assert "device_addresses" in tables
    assert "device_status_events" in tables
    assert "dns_queries" in tables
    assert "safety_alerts" in tables
    assert "audit_logs" in tables
    assert "alembic_version" in tables

    # Verify column presence in devices
    cur.execute("PRAGMA table_info(devices);")
    cols = {r[1] for r in cur.fetchall()}
    assert {"device_id", "friendly_name", "device_type", "primary_mac", "status"}.issubset(cols)

    # Verify column presence in dns_queries
    cur.execute("PRAGMA table_info(dns_queries);")
    q_cols = {r[1] for r in cur.fetchall()}
    assert {"id", "occurred_at", "source_ip", "device_id", "domain", "query_type", "dns_visibility"}.issubset(q_cols)

    conn.close()

    # 3. Test downgrade to base
    run_downgrade("base", db_url)

    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables_after = {r[0] for r in cur.fetchall()}
    assert "devices" not in tables_after
    assert "dns_queries" not in tables_after
    conn.close()

    # 4. Re-upgrade to head to verify idempotent re-run
    run_upgrade_head(db_url)
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    recreated = {r[0] for r in cur.fetchall()}
    assert "devices" in recreated
    assert "dns_queries" in recreated
    conn.close()
