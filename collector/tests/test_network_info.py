from __future__ import annotations

from collector.device_discovery import network_info

ROUTE_OUTPUT_SIMPLE = """\
default via 192.168.1.1 dev wlan0 proto dhcp metric 600
192.168.1.0/24 dev wlan0 proto kernel scope link src 192.168.1.42 metric 600
169.254.0.0/16 dev wlan0 scope link metric 1000
"""

ROUTE_OUTPUT_MULTI_INTERFACE = """\
default via 10.0.0.1 dev eth0 proto dhcp metric 100
10.0.0.0/24 dev eth0 proto kernel scope link src 10.0.0.55 metric 100
192.168.1.0/24 dev wlan0 proto kernel scope link src 192.168.1.42 metric 600
"""

ROUTE_OUTPUT_NO_DEFAULT = """\
192.168.1.0/24 dev wlan0 proto kernel scope link src 192.168.1.42 metric 600
"""

ADDR_OUTPUT_WLAN0 = """\
3: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default qlen 1000
    link/ether 11:22:33:44:55:66 brd ff:ff:ff:ff:ff:ff
    inet 192.168.1.42/24 brd 192.168.1.255 scope global dynamic noprefixroute wlan0
       valid_lft 3451sec preferred_lft 3451sec
    inet6 2a01:cb19:1234:5678:aaaa:bbbb:cccc:dddd/64 scope global temporary dynamic
       valid_lft 3451sec preferred_lft 3451sec
    inet6 fe80::1234:5678:9abc:def0/64 scope link noprefixroute
       valid_lft forever preferred_lft forever
"""

ADDR_OUTPUT_NO_IPV6 = """\
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP group default qlen 1000
    link/ether aa:bb:cc:dd:ee:ff brd ff:ff:ff:ff:ff:ff
    inet 10.0.0.55/24 brd 10.0.0.255 scope global dynamic noprefixroute eth0
       valid_lft 3451sec preferred_lft 3451sec
"""

ADDR_OUTPUT_NO_IPV4 = """\
4: wlan0: <BROADCAST,MULTICAST> mtu 1500 qdisc noqueue state DOWN group default qlen 1000
    link/ether 11:22:33:44:55:66 brd ff:ff:ff:ff:ff:ff
"""


def test_parse_default_route_extracts_gateway_and_interface():
    gateway, interface = network_info._parse_default_route(ROUTE_OUTPUT_SIMPLE)
    assert gateway == "192.168.1.1"
    assert interface == "wlan0"


def test_parse_default_route_returns_none_when_absent():
    gateway, interface = network_info._parse_default_route(ROUTE_OUTPUT_NO_DEFAULT)
    assert gateway is None
    assert interface is None


def test_parse_default_route_picks_the_right_interface_among_several():
    gateway, interface = network_info._parse_default_route(ROUTE_OUTPUT_MULTI_INTERFACE)
    assert gateway == "10.0.0.1"
    assert interface == "eth0"


def test_parse_subnet_for_interface_prefers_scope_link():
    subnet = network_info._parse_subnet_for_interface(ROUTE_OUTPUT_SIMPLE, "wlan0")
    assert subnet == "192.168.1.0/24"


def test_parse_subnet_ignores_other_interfaces():
    subnet = network_info._parse_subnet_for_interface(ROUTE_OUTPUT_MULTI_INTERFACE, "wlan0")
    assert subnet == "192.168.1.0/24"
    subnet_eth0 = network_info._parse_subnet_for_interface(ROUTE_OUTPUT_MULTI_INTERFACE, "eth0")
    assert subnet_eth0 == "10.0.0.0/24"


def test_parse_subnet_returns_none_for_unknown_interface():
    assert network_info._parse_subnet_for_interface(ROUTE_OUTPUT_SIMPLE, "ppp0") is None


def test_parse_addr_show_extracts_mac_ipv4_and_ipv6():
    mac, ipv4, ipv6_globals = network_info._parse_addr_show(ADDR_OUTPUT_WLAN0)
    assert mac == "11:22:33:44:55:66"
    assert ipv4 == "192.168.1.42"
    assert ipv6_globals == ["2a01:cb19:1234:5678:aaaa:bbbb:cccc:dddd"]
    # link-local (scope link) address must NOT be treated as global
    assert "fe80::1234:5678:9abc:def0" not in ipv6_globals


def test_parse_addr_show_handles_no_ipv6():
    mac, ipv4, ipv6_globals = network_info._parse_addr_show(ADDR_OUTPUT_NO_IPV6)
    assert mac == "aa:bb:cc:dd:ee:ff"
    assert ipv4 == "10.0.0.55"
    assert ipv6_globals == []


def test_parse_addr_show_handles_no_ipv4_gracefully():
    mac, ipv4, ipv6_globals = network_info._parse_addr_show(ADDR_OUTPUT_NO_IPV4)
    assert mac == "11:22:33:44:55:66"
    assert ipv4 is None
    assert ipv6_globals == []


def test_detect_network_info_end_to_end(monkeypatch):
    """Exercise detect_network_info() without touching the real network by
    monkeypatching run_command to return fixture text.
    """

    def fake_run_command(args, timeout=5.0):
        if args[:3] == ["ip", "route", "show"]:
            return ROUTE_OUTPUT_SIMPLE
        if args[:3] == ["ip", "addr", "show"]:
            return ADDR_OUTPUT_WLAN0
        raise AssertionError(f"Unexpected command in test: {args}")

    monkeypatch.setattr(network_info, "run_command", fake_run_command)

    info = network_info.detect_network_info()
    assert info.interface == "wlan0"
    assert info.subnet_cidr == "192.168.1.0/24"
    assert info.gateway_ip == "192.168.1.1"
    assert info.mac_address == "11:22:33:44:55:66"
    assert info.local_ip == "192.168.1.42"
    assert info.ipv6_active is True


def test_detect_network_info_raises_when_no_interface_found(monkeypatch):
    monkeypatch.setattr(
        network_info, "run_command", lambda args, timeout=5.0: ROUTE_OUTPUT_NO_DEFAULT
    )
    try:
        network_info.detect_network_info()
        assert False, "expected NetworkDetectionError"
    except network_info.NetworkDetectionError as exc:
        assert "DISCOVERY_INTERFACE" in str(exc)


def test_detect_network_info_respects_preferred_interface_override(monkeypatch):
    def fake_run_command(args, timeout=5.0):
        if args[:3] == ["ip", "route", "show"]:
            return ROUTE_OUTPUT_MULTI_INTERFACE
        if args == ["ip", "addr", "show", "wlan0"]:
            return ADDR_OUTPUT_WLAN0
        raise AssertionError(f"Unexpected command in test: {args}")

    monkeypatch.setattr(network_info, "run_command", fake_run_command)

    # Without override, the default route (eth0) would win; force wlan0 instead.
    info = network_info.detect_network_info(preferred_interface="wlan0")
    assert info.interface == "wlan0"
    assert info.subnet_cidr == "192.168.1.0/24"
