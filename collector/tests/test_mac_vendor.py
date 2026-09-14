from __future__ import annotations

import pytest

from collector.device_discovery import mac_vendor


@pytest.mark.parametrize(
    "mac,expected",
    [
        ("02:00:00:00:00:00", True),   # classic randomized-address prefix
        ("06:11:22:33:44:55", True),   # 0x06 & 0x02 -> bit set
        ("AA:BB:CC:DD:EE:FF", True),   # 0xAA & 0x02 -> bit set
        ("00:1A:2B:00:00:00", False),  # 0x00 & 0x02 -> not set (globally unique)
        ("A8:11:22:33:44:55", False),  # 0xA8 & 0x02 -> not set, despite "looking random"
        ("d4-3d-7e-11-22-33", False),  # lowercase + dash separators, still parses
    ],
)
def test_is_locally_administered(mac, expected):
    assert mac_vendor.is_locally_administered(mac) is expected


def test_normalize_mac_uppercases_and_converts_dashes():
    assert mac_vendor.normalize_mac("aa-bb-cc-dd-ee-ff") == "AA:BB:CC:DD:EE:FF"


def test_normalize_mac_rejects_garbage():
    with pytest.raises(mac_vendor.InvalidMacAddressError):
        mac_vendor.normalize_mac("not-a-mac-address")


def test_normalize_mac_rejects_wrong_length():
    with pytest.raises(mac_vendor.InvalidMacAddressError):
        mac_vendor.normalize_mac("AA:BB:CC:DD:EE")


def test_describe_randomized_mac_has_no_vendor_even_with_database():
    # A locally-administered MAC should never be reported with a vendor
    # name, even if its prefix happens to collide with something in the
    # database — the U/L bit means the OUI portion isn't meaningful.
    database = {"020000": "Should Not Appear"}
    info = mac_vendor.describe("02:00:00:11:22:33", oui_database=database)
    assert info.is_locally_administered is True
    assert info.vendor is None


def test_describe_without_database_returns_no_vendor():
    info = mac_vendor.describe("00:1A:2B:00:00:00", oui_database=None)
    assert info.is_locally_administered is False
    assert info.vendor is None


def test_describe_with_database_returns_matching_vendor():
    database = {"001A2B": "Example Vendor Inc"}
    info = mac_vendor.describe("00:1A:2B:99:88:77", oui_database=database)
    assert info.vendor == "Example Vendor Inc"


def test_load_oui_database_parses_real_ieee_format(tmp_path):
    sample = (
        "\n"
        "00-1A-2B   (hex)\t\tExample Vendor Inc\n"
        "001A2B     (base 16)\t\tExample Vendor Inc\n"
        "\t\t\t123 Example Street\n"
        "\n"
        "F4-F5-E8   (hex)\t\tAnother Vendor LLC\n"
        "F4F5E8     (base 16)\t\tAnother Vendor LLC\n"
    )
    oui_file = tmp_path / "oui.txt"
    oui_file.write_text(sample, encoding="utf-8")

    database = mac_vendor.load_oui_database(str(oui_file))
    assert database["001A2B"] == "Example Vendor Inc"
    assert database["F4F5E8"] == "Another Vendor LLC"


def test_load_oui_database_missing_file_raises():
    with pytest.raises(OSError):
        mac_vendor.load_oui_database("/nonexistent/path/oui.txt")
