from __future__ import annotations

import socket
import subprocess

from collector.device_discovery import hostname_resolver


def test_reverse_dns_lookup_returns_hostname_on_success(monkeypatch):
    monkeypatch.setattr(
        socket, "gethostbyaddr", lambda ip: ("_gateway", [], [ip])
    )
    assert hostname_resolver.reverse_dns_lookup("192.168.1.1") == "_gateway"


def test_reverse_dns_lookup_returns_none_on_herror(monkeypatch):
    def raise_herror(ip):
        raise socket.herror("unknown host")

    monkeypatch.setattr(socket, "gethostbyaddr", raise_herror)
    assert hostname_resolver.reverse_dns_lookup("192.168.1.50") is None


def test_reverse_dns_lookup_returns_none_on_timeout(monkeypatch):
    def raise_timeout(ip):
        raise socket.timeout("timed out")

    monkeypatch.setattr(socket, "gethostbyaddr", raise_timeout)
    assert hostname_resolver.reverse_dns_lookup("192.168.1.50") is None


def test_reverse_dns_lookup_restores_default_timeout_even_on_failure(monkeypatch):
    monkeypatch.setattr(socket, "gethostbyaddr", lambda ip: (_ for _ in ()).throw(socket.herror()))
    original = socket.getdefaulttimeout()
    hostname_resolver.reverse_dns_lookup("192.168.1.50", timeout=0.5)
    assert socket.getdefaulttimeout() == original


def test_mdns_reverse_lookup_parses_successful_output(monkeypatch):
    def fake_run(args, capture_output, text, timeout, check):
        assert args == ["avahi-resolve", "-a", "192.168.1.60"]
        return subprocess.CompletedProcess(
            args, returncode=0, stdout="192.168.1.60\tGalaxy-S23.local\n", stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hostname_resolver.mdns_reverse_lookup("192.168.1.60") == "Galaxy-S23.local"


def test_mdns_reverse_lookup_returns_none_when_avahi_not_installed(monkeypatch):
    def fake_run(*a, **k):
        raise FileNotFoundError("avahi-resolve not found")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hostname_resolver.mdns_reverse_lookup("192.168.1.60") is None


def test_mdns_reverse_lookup_returns_none_on_nonzero_exit(monkeypatch):
    def fake_run(*a, **k):
        return subprocess.CompletedProcess(a, returncode=1, stdout="", stderr="Failed to resolve")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hostname_resolver.mdns_reverse_lookup("192.168.1.61") is None


def test_mdns_reverse_lookup_returns_none_on_timeout(monkeypatch):
    def fake_run(*a, **k):
        raise subprocess.TimeoutExpired(cmd="avahi-resolve", timeout=1.0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hostname_resolver.mdns_reverse_lookup("192.168.1.61") is None


def test_mdns_reverse_lookup_returns_none_on_malformed_output(monkeypatch):
    def fake_run(*a, **k):
        return subprocess.CompletedProcess(a, returncode=0, stdout="garbage-with-no-tab\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert hostname_resolver.mdns_reverse_lookup("192.168.1.61") is None


def test_resolve_hostname_prefers_reverse_dns_over_mdns(monkeypatch):
    monkeypatch.setattr(hostname_resolver, "reverse_dns_lookup", lambda ip: "_gateway")
    monkeypatch.setattr(
        hostname_resolver, "mdns_reverse_lookup", lambda ip: (_ for _ in ()).throw(
            AssertionError("mDNS should not be tried when reverse DNS already succeeded")
        )
    )
    assert hostname_resolver.resolve_hostname("192.168.1.1") == "_gateway"


def test_resolve_hostname_falls_back_to_mdns(monkeypatch):
    monkeypatch.setattr(hostname_resolver, "reverse_dns_lookup", lambda ip: None)
    monkeypatch.setattr(hostname_resolver, "mdns_reverse_lookup", lambda ip: "iPhone.local")
    assert hostname_resolver.resolve_hostname("192.168.1.70") == "iPhone.local"


def test_resolve_hostname_returns_none_when_both_fail(monkeypatch):
    monkeypatch.setattr(hostname_resolver, "reverse_dns_lookup", lambda ip: None)
    monkeypatch.setattr(hostname_resolver, "mdns_reverse_lookup", lambda ip: None)
    assert hostname_resolver.resolve_hostname("192.168.1.80") is None
