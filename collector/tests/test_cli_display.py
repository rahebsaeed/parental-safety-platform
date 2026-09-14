from __future__ import annotations

from collector.device_discovery import cli, storage


def _device(**overrides):
    base = dict(
        device_id="dev_01",
        friendly_name=None,
        device_type=None,
        primary_mac="AA:BB:CC:DD:EE:FF",
        mac_is_randomized=False,
        vendor=None,
        status="online",
        confidence="HIGH",
        first_seen="2026-09-12T08:00:00+00:00",
        last_seen="2026-09-12T08:00:00+00:00",
    )
    base.update(overrides)
    return storage.DeviceRecord(**base)


def test_table_includes_vendor_column_header():
    table = cli._format_devices_table([_device(vendor="Samsung Electronics")])
    assert "VENDOR" in table
    assert "Samsung Electronics" in table


def test_table_shows_placeholder_for_unknown_vendor():
    table = cli._format_devices_table([_device(vendor=None)])
    assert "(unknown)" in table


def test_table_truncates_long_vendor_names():
    long_name = "A Very Long Manufacturer Name That Would Otherwise Break The Table"
    table = cli._format_devices_table([_device(vendor=long_name)])
    assert long_name not in table
    assert "…" in table


def test_truncate_leaves_short_strings_untouched():
    assert cli._truncate("Apple", max_len=22) == "Apple"


def test_truncate_cuts_and_marks_long_strings():
    result = cli._truncate("X" * 30, max_len=10)
    assert len(result) == 10
    assert result.endswith("…")


def test_empty_device_list_still_returns_a_message_not_an_error():
    assert "No devices" in cli._format_devices_table([])
