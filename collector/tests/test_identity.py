from __future__ import annotations

from collector.device_discovery.identity import (
    Confidence,
    KnownDevice,
    Observation,
    match_device,
)


def test_new_device_with_no_known_devices_and_mac_is_medium():
    result = match_device(
        Observation(ip="192.168.1.50", mac="AA:BB:CC:DD:EE:FF", hostname=None),
        known_devices=[],
    )
    assert result.device_id is None
    assert result.confidence == Confidence.MEDIUM


def test_new_device_with_no_mac_at_all_is_low():
    result = match_device(
        Observation(ip="192.168.1.50", mac=None, hostname=None), known_devices=[]
    )
    assert result.device_id is None
    assert result.confidence == Confidence.LOW
    assert "192.168.1.50" in result.reason


def test_returning_device_with_stable_mac_is_high_confidence():
    known = [KnownDevice(device_id="dev_01", primary_mac="AA:BB:CC:DD:EE:FF", last_hostname=None)]
    result = match_device(
        Observation(ip="192.168.1.50", mac="aa:bb:cc:dd:ee:ff", hostname=None),
        known_devices=known,
    )
    assert result.device_id == "dev_01"
    assert result.confidence == Confidence.HIGH


def test_mac_match_is_case_insensitive():
    known = [KnownDevice(device_id="dev_01", primary_mac="aa:bb:cc:dd:ee:ff", last_hostname=None)]
    result = match_device(
        Observation(ip="192.168.1.50", mac="AA:BB:CC:DD:EE:FF", hostname=None),
        known_devices=known,
    )
    assert result.device_id == "dev_01"
    assert result.confidence == Confidence.HIGH


def test_randomized_mac_that_matches_known_device_is_still_high():
    """Both Android (persistent-per-network) and iOS (Fixed on WPA2/WPA3)
    keep a private MAC stable per home network by default — see
    docs/architecture/phase-1-discovery.md. A repeat sighting of the same
    randomized MAC should be trusted, not permanently capped at LOW.
    """
    known = [KnownDevice(device_id="dev_02", primary_mac="02:11:22:33:44:55", last_hostname=None)]
    result = match_device(
        Observation(ip="192.168.1.60", mac="02:11:22:33:44:55", hostname=None),
        known_devices=known,
    )
    assert result.device_id == "dev_02"
    assert result.confidence == Confidence.HIGH
    assert result.mac_is_randomized is True


def test_mac_changed_but_specific_hostname_matches_is_medium():
    known = [
        KnownDevice(device_id="dev_03", primary_mac="11:11:11:11:11:11", last_hostname="galaxy-s23")
    ]
    result = match_device(
        Observation(ip="192.168.1.70", mac="22:22:22:22:22:22", hostname="galaxy-s23"),
        known_devices=known,
    )
    assert result.device_id == "dev_03"
    assert result.confidence == Confidence.MEDIUM


def test_generic_hostname_does_not_cause_false_match():
    known = [
        KnownDevice(device_id="dev_04", primary_mac="11:11:11:11:11:11", last_hostname="android")
    ]
    result = match_device(
        Observation(ip="192.168.1.80", mac="99:99:99:99:99:99", hostname="android"),
        known_devices=known,
    )
    # "android" is a generic hostname shared across many devices; must not
    # be used as a matching signal, or two different phones would merge.
    assert result.device_id is None


def test_two_devices_with_same_generic_hostname_stay_separate():
    known = [
        KnownDevice(device_id="dev_05", primary_mac="AA:AA:AA:AA:AA:AA", last_hostname="iphone"),
    ]
    result = match_device(
        Observation(ip="192.168.1.90", mac="BB:BB:BB:BB:BB:BB", hostname="iphone"),
        known_devices=known,
    )
    assert result.device_id is None  # correctly treated as a new/different device


def test_mac_takes_priority_over_conflicting_hostname():
    known = [
        KnownDevice(device_id="dev_06", primary_mac="AA:AA:AA:AA:AA:AA", last_hostname="old-name"),
        KnownDevice(device_id="dev_07", primary_mac="BB:BB:BB:BB:BB:BB", last_hostname="new-name"),
    ]
    # This MAC belongs to dev_06, even though the hostname now matches dev_07's —
    # a MAC match should win, since it's the stronger signal.
    result = match_device(
        Observation(ip="192.168.1.100", mac="aa:aa:aa:aa:aa:aa", hostname="new-name"),
        known_devices=known,
    )
    assert result.device_id == "dev_06"
    assert result.confidence == Confidence.HIGH


def test_malformed_mac_is_treated_as_no_mac():
    result = match_device(
        Observation(ip="192.168.1.110", mac="not-a-real-mac", hostname=None),
        known_devices=[],
    )
    assert result.device_id is None
    assert result.confidence == Confidence.LOW


def test_ip_only_placeholder_adopts_first_mac_seen_at_same_ip():
    """The DNS ingester creates MAC-less placeholder devices for IPs no
    scan has mapped yet. When a scan later observes a MAC at that same IP,
    it must enrich the placeholder — not create a duplicate device."""
    known = [
        KnownDevice(device_id="dev_10", primary_mac=None, last_hostname=None,
                    last_ip="192.168.1.15"),
    ]
    result = match_device(
        Observation(ip="192.168.1.15", mac="4c:0f:6e:95:32:12", hostname="Ahmed-PC"),
        known_devices=known,
    )
    assert result.device_id == "dev_10"
    assert result.confidence == Confidence.MEDIUM


def test_ip_adoption_does_not_fire_for_different_ip():
    known = [
        KnownDevice(device_id="dev_10", primary_mac=None, last_hostname=None,
                    last_ip="192.168.1.15"),
    ]
    result = match_device(
        Observation(ip="192.168.1.16", mac="4c:0f:6e:95:32:12", hostname=None),
        known_devices=known,
    )
    assert result.device_id is None  # new device, not a merge


def test_exact_mac_match_beats_ip_adoption():
    """A MAC already claimed by a real device always matches its owner,
    even if an IP-only placeholder sits at the observation IP."""
    known = [
        KnownDevice(device_id="dev_10", primary_mac=None, last_hostname=None,
                    last_ip="192.168.1.15"),
        KnownDevice(device_id="dev_03", primary_mac="AA:BB:CC:DD:EE:01",
                    last_hostname=None),
    ]
    result = match_device(
        Observation(ip="192.168.1.15", mac="aa:bb:cc:dd:ee:01", hostname=None),
        known_devices=known,
    )
    assert result.device_id == "dev_03"
    assert result.confidence == Confidence.HIGH
