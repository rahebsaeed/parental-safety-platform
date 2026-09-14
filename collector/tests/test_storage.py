from __future__ import annotations

import sqlite3

from collector.device_discovery import storage

T1 = "2026-09-11T10:00:00+00:00"
T2 = "2026-09-11T10:05:00+00:00"
T3 = "2026-09-11T10:10:00+00:00"


def test_create_device_assigns_sequential_ids(db_conn):
    id1 = storage.create_device(
        db_conn, primary_mac="AA:AA:AA:AA:AA:AA", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    id2 = storage.create_device(
        db_conn, primary_mac="BB:BB:BB:BB:BB:BB", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    assert id1 == "dev_01"
    assert id2 == "dev_02"


def test_new_device_starts_online(db_conn):
    device_id = storage.create_device(
        db_conn, primary_mac="AA:AA:AA:AA:AA:AA", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    device = storage.get_device(db_conn, device_id)
    assert device is not None
    assert device.status == "online"
    assert device.first_seen == T1
    assert device.last_seen == T1


def test_get_device_returns_none_for_unknown_id(db_conn):
    assert storage.get_device(db_conn, "dev_99") is None


def test_record_observation_updates_last_seen_and_adds_history(db_conn):
    device_id = storage.create_device(
        db_conn, primary_mac="AA:AA:AA:AA:AA:AA", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    storage.record_observation(
        db_conn, device_id=device_id, ip_address="192.168.1.50",
        mac_address="AA:AA:AA:AA:AA:AA", hostname="my-phone", vendor="Unknown",
        observed_at_iso=T2, confidence="HIGH",
    )
    device = storage.get_device(db_conn, device_id)
    assert device.last_seen == T2
    assert device.confidence == "HIGH"

    history = storage.get_ip_history(db_conn, device_id)
    assert len(history) == 1
    assert history[0].ip_address == "192.168.1.50"
    assert history[0].hostname == "my-phone"


def test_ip_history_is_most_recent_first(db_conn):
    device_id = storage.create_device(
        db_conn, primary_mac="AA:AA:AA:AA:AA:AA", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    storage.record_observation(
        db_conn, device_id=device_id, ip_address="192.168.1.50",
        mac_address="AA:AA:AA:AA:AA:AA", hostname=None, vendor=None,
        observed_at_iso=T1, confidence="MEDIUM",
    )
    storage.record_observation(
        db_conn, device_id=device_id, ip_address="192.168.1.51",  # DHCP reassigned the IP
        mac_address="AA:AA:AA:AA:AA:AA", hostname=None, vendor=None,
        observed_at_iso=T2, confidence="HIGH",
    )
    history = storage.get_ip_history(db_conn, device_id)
    assert [h.ip_address for h in history] == ["192.168.1.51", "192.168.1.50"]


def test_mark_offline_except_only_affects_absent_devices(db_conn):
    id1 = storage.create_device(
        db_conn, primary_mac="AA:AA:AA:AA:AA:AA", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    id2 = storage.create_device(
        db_conn, primary_mac="BB:BB:BB:BB:BB:BB", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    newly_offline = storage.mark_offline_except(db_conn, seen_device_ids={id1}, occurred_at_iso=T2)

    assert newly_offline == [id2]
    assert storage.get_device(db_conn, id1).status == "online"
    assert storage.get_device(db_conn, id2).status == "offline"


def test_device_that_returns_after_being_offline_logs_online_event(db_conn):
    device_id = storage.create_device(
        db_conn, primary_mac="AA:AA:AA:AA:AA:AA", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    storage.mark_offline_except(db_conn, seen_device_ids=set(), occurred_at_iso=T2)
    assert storage.get_device(db_conn, device_id).status == "offline"

    storage.record_observation(
        db_conn, device_id=device_id, ip_address="192.168.1.50",
        mac_address="AA:AA:AA:AA:AA:AA", hostname=None, vendor=None,
        observed_at_iso=T3, confidence="HIGH",
    )
    device = storage.get_device(db_conn, device_id)
    assert device.status == "online"

    events = db_conn.execute(
        "SELECT status, occurred_at FROM device_status_events WHERE device_id = ? ORDER BY occurred_at",
        (device_id,),
    ).fetchall()
    statuses = [(row["status"], row["occurred_at"]) for row in events]
    assert statuses == [("offline", T2), ("online", T3)]


def test_set_friendly_name_and_classify(db_conn):
    device_id = storage.create_device(
        db_conn, primary_mac="AA:AA:AA:AA:AA:AA", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    assert storage.set_friendly_name(db_conn, device_id, "Samsung Phone") is True
    assert storage.set_device_type(db_conn, device_id, "Android") is True

    device = storage.get_device(db_conn, device_id)
    assert device.friendly_name == "Samsung Phone"
    assert device.device_type == "Android"


def test_set_friendly_name_on_unknown_device_returns_false(db_conn):
    assert storage.set_friendly_name(db_conn, "dev_99", "Ghost Device") is False


def test_get_known_devices_for_matching_includes_last_hostname(db_conn):
    device_id = storage.create_device(
        db_conn, primary_mac="AA:AA:AA:AA:AA:AA", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    storage.record_observation(
        db_conn, device_id=device_id, ip_address="192.168.1.50",
        mac_address="AA:AA:AA:AA:AA:AA", hostname="my-phone", vendor=None,
        observed_at_iso=T1, confidence="HIGH",
    )
    known = storage.get_known_devices_for_matching(db_conn)
    assert len(known) == 1
    assert known[0].device_id == device_id
    assert known[0].primary_mac == "AA:AA:AA:AA:AA:AA"
    assert known[0].last_hostname == "my-phone"


def test_get_all_devices_orders_by_device_id(db_conn):
    storage.create_device(
        db_conn, primary_mac="BB:BB:BB:BB:BB:BB", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    storage.create_device(
        db_conn, primary_mac="AA:AA:AA:AA:AA:AA", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    devices = storage.get_all_devices(db_conn)
    assert [d.device_id for d in devices] == ["dev_01", "dev_02"]


def test_record_observation_rolls_up_vendor_onto_device(db_conn):
    """Regression test: vendor was being stored per-observation but never
    surfaced on the device itself, so `list`/`scan` had no way to show it
    even when --oui-file resolved a real manufacturer name.
    """
    device_id = storage.create_device(
        db_conn, primary_mac="70:AF:09:D4:41:DC", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    storage.record_observation(
        db_conn, device_id=device_id, ip_address="192.168.1.2",
        mac_address="70:AF:09:D4:41:DC", hostname=None,
        vendor="Some Real Vendor Inc", observed_at_iso=T1, confidence="HIGH",
    )
    device = storage.get_device(db_conn, device_id)
    assert device.vendor == "Some Real Vendor Inc"


def test_record_observation_without_vendor_does_not_clear_existing_one(db_conn):
    device_id = storage.create_device(
        db_conn, primary_mac="AA:AA:AA:AA:AA:AA", mac_is_randomized=False,
        confidence="MEDIUM", now_iso=T1,
    )
    storage.record_observation(
        db_conn, device_id=device_id, ip_address="192.168.1.50",
        mac_address="AA:AA:AA:AA:AA:AA", hostname=None,
        vendor="Known Vendor Co", observed_at_iso=T1, confidence="HIGH",
    )
    # A later observation with no vendor info available (e.g. no --oui-file
    # this run) shouldn't overwrite a previously-known vendor with nothing.
    storage.record_observation(
        db_conn, device_id=device_id, ip_address="192.168.1.50",
        mac_address="AA:AA:AA:AA:AA:AA", hostname=None,
        vendor=None, observed_at_iso=T2, confidence="HIGH",
    )
    assert storage.get_device(db_conn, device_id).vendor == "Known Vendor Co"


def test_new_database_has_vendor_column_from_the_start(db_conn):
    columns = {row["name"] for row in db_conn.execute("PRAGMA table_info(devices)").fetchall()}
    assert "vendor" in columns


def test_migration_adds_vendor_column_to_a_pre_existing_database_without_losing_data(tmp_path):
    """Reproduces exactly what happened to a real user: a database created
    before the vendor column existed must gain it in place, keeping every
    device, name, and classification already stored.
    """
    db_path = tmp_path / "pre_existing.sqlite3"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE devices (
            device_id TEXT PRIMARY KEY,
            friendly_name TEXT,
            device_type TEXT,
            primary_mac TEXT,
            mac_is_randomized INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'online',
            confidence TEXT NOT NULL DEFAULT 'LOW',
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO devices (device_id, friendly_name, device_type, primary_mac, "
        "status, confidence, first_seen, last_seen) VALUES "
        "('dev_05', 'S24Ultra', 'Android', '4E:61:BA:9C:81:6A', 'online', 'HIGH', ?, ?)",
        (T1, T1),
    )
    conn.commit()
    conn.close()

    # Simulate re-opening this pre-existing database with the new code.
    migrated_conn = storage.init_db(db_path)
    device = storage.get_device(migrated_conn, "dev_05")
    migrated_conn.close()

    assert device is not None
    assert device.friendly_name == "S24Ultra"  # existing data preserved
    assert device.device_type == "Android"
    assert device.vendor is None  # new column, no value yet, but present and queryable
