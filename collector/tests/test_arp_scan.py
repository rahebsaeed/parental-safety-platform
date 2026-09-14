from __future__ import annotations

from collector.device_discovery import arp_scan

NEIGH_V4_OUTPUT = """\
192.168.1.1 dev wlan0 lladdr aa:bb:cc:dd:ee:ff STALE
192.168.1.15 dev wlan0 lladdr 22:33:44:55:66:77 REACHABLE
192.168.1.20 dev wlan0 FAILED
192.168.1.42 dev wlan0 lladdr 11:22:33:44:55:66 PERMANENT
"""

NEIGH_V6_OUTPUT = """\
fe80::1 dev wlan0 lladdr aa:bb:cc:dd:ee:ff router STALE
2a01:cb19:1234:5678::1 dev wlan0 lladdr aa:bb:cc:dd:ee:ff router REACHABLE
fe80::9abc:def0 dev wlan0 lladdr 22:33:44:55:66:77 STALE
fe80::dead:beef dev wlan0 INCOMPLETE
"""

NEIGH_MULTI_INTERFACE = """\
192.168.1.1 dev wlan0 lladdr aa:bb:cc:dd:ee:ff STALE
10.0.0.1 dev eth0 lladdr 99:88:77:66:55:44 REACHABLE
"""


def test_parse_neighbor_lines_v4_skips_unresolved_entries():
    results = arp_scan._parse_neighbor_lines(NEIGH_V4_OUTPUT)
    ips = {r.ip for r in results}
    assert ips == {"192.168.1.1", "192.168.1.15", "192.168.1.42"}
    assert "192.168.1.20" not in ips  # FAILED, no lladdr -> correctly excluded


def test_parse_neighbor_lines_v4_extracts_mac_and_interface():
    results = arp_scan._parse_neighbor_lines(NEIGH_V4_OUTPUT)
    by_ip = {r.ip: r for r in results}
    assert by_ip["192.168.1.1"].mac == "aa:bb:cc:dd:ee:ff"
    assert by_ip["192.168.1.1"].interface == "wlan0"
    assert by_ip["192.168.1.1"].source == "passive_neighbor_cache"


def test_parse_neighbor_lines_v6_handles_router_flag_and_incomplete():
    results = arp_scan._parse_neighbor_lines(NEIGH_V6_OUTPUT)
    ips = {r.ip for r in results}
    assert "fe80::1" in ips
    assert "2a01:cb19:1234:5678::1" in ips
    assert "fe80::9abc:def0" in ips
    assert "fe80::dead:beef" not in ips  # INCOMPLETE, no lladdr


def test_parse_neighbor_lines_v6_mac_extracted_despite_router_token():
    results = arp_scan._parse_neighbor_lines(NEIGH_V6_OUTPUT)
    by_ip = {r.ip: r for r in results}
    assert by_ip["fe80::1"].mac == "aa:bb:cc:dd:ee:ff"


def test_parse_neighbor_lines_respects_interface_filter():
    results = arp_scan._parse_neighbor_lines(NEIGH_MULTI_INTERFACE, interface_filter="eth0")
    assert len(results) == 1
    assert results[0].ip == "10.0.0.1"


def test_parse_neighbor_lines_empty_input():
    assert arp_scan._parse_neighbor_lines("") == []


def test_parse_neighbor_lines_ignores_blank_lines():
    text = "\n\n192.168.1.1 dev wlan0 lladdr aa:bb:cc:dd:ee:ff STALE\n\n"
    results = arp_scan._parse_neighbor_lines(text)
    assert len(results) == 1


def test_read_passive_neighbors_combines_v4_and_v6(monkeypatch):
    def fake_run_command(args, timeout=5.0):
        if args == ["ip", "neigh", "show"]:
            return NEIGH_V4_OUTPUT
        if args == ["ip", "-6", "neigh", "show"]:
            return NEIGH_V6_OUTPUT
        raise AssertionError(f"unexpected command {args}")

    monkeypatch.setattr(arp_scan, "run_command", fake_run_command)
    results = arp_scan.read_passive_neighbors()
    ips = {r.ip for r in results}
    assert "192.168.1.1" in ips
    assert "fe80::1" in ips


def test_read_passive_neighbors_survives_ipv6_command_failure(monkeypatch):
    """If `ip -6 neigh show` fails (e.g. IPv6 disabled), IPv4 discovery
    must still succeed rather than the whole function raising.
    """

    def fake_run_command(args, timeout=5.0):
        if args == ["ip", "neigh", "show"]:
            return NEIGH_V4_OUTPUT
        raise arp_scan.CommandExecutionError("ipv6 disabled")

    monkeypatch.setattr(arp_scan, "run_command", fake_run_command)
    results = arp_scan.read_passive_neighbors()
    assert {r.ip for r in results} == {"192.168.1.1", "192.168.1.15", "192.168.1.42"}


def test_discover_hosts_falls_back_to_passive_when_active_unavailable(monkeypatch):
    def fake_active_scan(interface, subnet_cidr, timeout=3.0):
        raise arp_scan.ActiveScanUnavailableError("no privileges in test")

    monkeypatch.setattr(arp_scan, "active_arp_scan", fake_active_scan)
    monkeypatch.setattr(arp_scan, "read_passive_neighbors", lambda interface=None: [
        arp_scan.RawNeighbor(ip="192.168.1.1", mac="aa:bb:cc:dd:ee:ff", interface="wlan0", source="passive_neighbor_cache")
    ])

    result = arp_scan.discover_hosts("wlan0", "192.168.1.0/24", attempt_active=True)
    assert result.active_scan_attempted is True
    assert result.active_scan_succeeded is False
    assert result.unavailable_reason == "no privileges in test"
    assert len(result.neighbors) == 1


def test_discover_hosts_active_results_take_priority_over_passive(monkeypatch):
    active_result = arp_scan.RawNeighbor(
        ip="192.168.1.1", mac="fresh:mac:from:active:scan:00", interface="wlan0", source="active_arp"
    )
    stale_passive = arp_scan.RawNeighbor(
        ip="192.168.1.1", mac="stale:cached:mac:00:00:00", interface="wlan0", source="passive_neighbor_cache"
    )
    monkeypatch.setattr(arp_scan, "active_arp_scan", lambda i, s, timeout=3.0: [active_result])
    monkeypatch.setattr(arp_scan, "read_passive_neighbors", lambda interface=None: [stale_passive])

    result = arp_scan.discover_hosts("wlan0", "192.168.1.0/24", attempt_active=True)
    assert len(result.neighbors) == 1
    assert result.neighbors[0].source == "active_arp"


def test_discover_hosts_without_attempting_active_is_passive_only(monkeypatch):
    monkeypatch.setattr(arp_scan, "read_passive_neighbors", lambda interface=None: [
        arp_scan.RawNeighbor(ip="192.168.1.1", mac="aa:bb:cc:dd:ee:ff", interface="wlan0", source="passive_neighbor_cache")
    ])
    result = arp_scan.discover_hosts("wlan0", "192.168.1.0/24", attempt_active=False)
    assert result.active_scan_attempted is False
    assert result.active_scan_succeeded is False
    assert result.unavailable_reason is None
