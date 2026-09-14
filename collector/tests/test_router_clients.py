from __future__ import annotations

from collector.device_discovery.router_clients import parse_client_list_page

SAMPLE_PAGE = """var LeaseNum='3';
var dhcpClient0_ip='192.168.1.7';
var dhcpClient0_mac='b0:81:01:74:72:a1';
var dhcpClient0_hostname='HONOR&#45;X8a';
var dhcpClient0_type='Ethernet';
var dhcpClient0_active='1';
var dhcpClient1_ip='192.168.1.5';
var dhcpClient1_mac='4e:61:ba:9c:81:6a';
var dhcpClient1_hostname='S24&#45;Ultra';
var dhcpClient1_type='Ethernet';
var dhcpClient1_active='1';
var dhcpClient2_ip='192.168.1.9';
var dhcpClient2_mac='aa:bb:cc:dd:ee:ff';
var dhcpClient2_hostname='old-phone';
var dhcpClient2_type='Ethernet';
var dhcpClient2_active='0';
var dhcpClient3_ip='';
var dhcpClient3_mac='';
var dhcpClient3_hostname='';
var dhcpClient3_type='';
var dhcpClient3_active='';
"""


def test_parses_active_leases_and_decodes_entities():
    clients = parse_client_list_page(SAMPLE_PAGE)
    assert [(c.ip, c.mac, c.hostname) for c in clients] == [
        ("192.168.1.7", "b0:81:01:74:72:a1", "HONOR-X8a"),
        ("192.168.1.5", "4e:61:ba:9c:81:6a", "S24-Ultra"),
    ]


def test_skips_inactive_and_empty_rows():
    clients = parse_client_list_page(SAMPLE_PAGE)
    ips = [c.ip for c in clients]
    assert "192.168.1.9" not in ips  # active='0' is a stale lease, not a device
    assert "" not in ips


def test_empty_or_garbage_page_yields_no_clients():
    assert parse_client_list_page("") == []
    assert parse_client_list_page("<html>login required</html>") == []


def test_missing_hostname_is_none_not_empty_string():
    page = (
        "var dhcpClient0_ip='192.168.1.2';"
        "var dhcpClient0_mac='70:af:09:d4:41:dc';"
        "var dhcpClient0_hostname='';"
        "var dhcpClient0_active='1';"
    )
    (client,) = parse_client_list_page(page)
    assert client.hostname is None


def test_discovery_cycle_merges_router_only_device(monkeypatch, db_conn):
    """A lease the ARP scan missed must still be recorded, and an ARP-seen
    lease must not be recorded twice."""
    from collector.device_discovery import arp_scan, discovery_service, router_clients
    from collector.device_discovery.network_info import NetworkInfo

    monkeypatch.setattr(
        arp_scan,
        "discover_hosts",
        lambda *a, **k: arp_scan.DiscoveryResult(
            neighbors=[
                arp_scan.RawNeighbor(
                    ip="192.168.1.2", mac="70:af:09:d4:41:dc",
                    interface="eth0", source="active_arp",
                )
            ],
            active_scan_attempted=True,
            active_scan_succeeded=True,
            unavailable_reason=None,
        ),
    )
    monkeypatch.setattr(
        discovery_service.hostname_resolver,
        "resolve_hostname",
        lambda ip: None,
    )
    monkeypatch.setattr(
        router_clients,
        "get_router_clients",
        lambda: [
            router_clients.RouterClient(
                ip="192.168.1.2", mac="70:af:09:d4:41:dc", hostname="esp32",
            ),
            router_clients.RouterClient(
                ip="192.168.1.5", mac="4e:61:ba:9c:81:6a", hostname="S24-Ultra",
            ),
        ],
    )

    network = NetworkInfo(
        interface="eth0", local_ip="192.168.1.20",
        subnet_cidr="192.168.1.0/24", gateway_ip="192.168.1.1",
        mac_address=None, ipv6_active=False, ipv6_global_addresses=(),
    )
    summary = discovery_service.run_discovery_cycle(
        db_conn, network, attempt_active=True
    )

    assert summary.devices_seen == 2
    by_mac = {
        (d.primary_mac or "").lower(): d
        for d in summary.devices
    }
    assert "70:af:09:d4:41:dc" in by_mac  # from ARP, not duplicated by router
    assert "4e:61:ba:9c:81:6a" in by_mac  # router-only lease discovered


def test_discovery_cycle_survives_router_failure(monkeypatch, db_conn):
    """Router fetch blowing up must degrade to ARP-only, never fail the scan."""
    from collector.device_discovery import arp_scan, discovery_service, router_clients
    from collector.device_discovery.network_info import NetworkInfo

    monkeypatch.setattr(
        arp_scan,
        "discover_hosts",
        lambda *a, **k: arp_scan.DiscoveryResult(
            neighbors=[
                arp_scan.RawNeighbor(
                    ip="192.168.1.2", mac="70:af:09:d4:41:dc",
                    interface="eth0", source="active_arp",
                )
            ],
            active_scan_attempted=True,
            active_scan_succeeded=True,
            unavailable_reason=None,
        ),
    )
    monkeypatch.setattr(
        discovery_service.hostname_resolver,
        "resolve_hostname",
        lambda ip: None,
    )

    def _boom():
        raise RuntimeError("router exploded")

    monkeypatch.setattr(router_clients, "get_router_clients", _boom)

    network = NetworkInfo(
        interface="eth0", local_ip="192.168.1.20",
        subnet_cidr="192.168.1.0/24", gateway_ip="192.168.1.1",
        mac_address=None, ipv6_active=False, ipv6_global_addresses=(),
    )
    # get_router_clients itself swallows errors, but even a raw raise from
    # the seam must not propagate out of the cycle:
    try:
        summary = discovery_service.run_discovery_cycle(
            db_conn, network, attempt_active=True
        )
    except RuntimeError:
        # If the seam ever stops swallowing, the cycle must still guard it.
        # Fail loudly here so the regression is caught, not silent.
        raise AssertionError("run_discovery_cycle propagated a router failure")
    assert summary.devices_seen == 1
