"""Tests for the Router DNS control API.

Manual-only model: the status/switch endpoints must never 500 on router
trouble (unreachable -> mode="unreachable" / HTTP 502), must reject bad
modes with 422, must delegate switching to the canonical router-dns.sh
script, and must maintain the 3h failsafe deadline (ON writes it,
OFF clears it, status reports the countdown).
"""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from backend.app.api.routers import router_dns
from backend.app.main import app


@pytest.fixture(scope="function")
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


class FakeResponse:
    def __init__(self, text="", status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")


def _fake_session(monkeypatch, page_text):
    class FakeSession:
        def __init__(self):
            self.headers = {}

        def get(self, url, params=None, timeout=None):
            if "Login.asp" in url:
                return FakeResponse("ok")
            return FakeResponse(page_text)

    monkeypatch.setattr(router_dns.requests, "Session", FakeSession)


def test_mode_mapping():
    assert router_dns._mode_for("192.168.1.20", "192.168.1.20") == "dnsmasq"
    assert router_dns._mode_for("192.168.1.1", "192.168.1.1") == "router"
    assert router_dns._mode_for("192.168.1.20", "192.168.1.1") == "custom"
    assert router_dns._mode_for(None, None) == "unknown"


def test_status_dnsmasq_mode(client, monkeypatch):
    _fake_session(monkeypatch, '{"pridns":"192.168.1.20","secdns":"192.168.1.20"}')
    resp = client.get("/api/router-dns/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "dnsmasq"
    assert body["pridns"] == "192.168.1.20"


def test_status_unreachable_degrades_not_500(client, monkeypatch):
    import requests

    class DeadSession:
        def __init__(self):
            self.headers = {}

        def get(self, *a, **k):
            raise requests.exceptions.ConnectTimeout("no route")

    monkeypatch.setattr(router_dns.requests, "Session", DeadSession)
    resp = client.get("/api/router-dns/status")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "unreachable"


def test_switch_rejects_bad_mode(client):
    resp = client.post("/api/router-dns/mode", json={"mode": "opendns"})
    assert resp.status_code == 422


def test_switch_delegates_to_script(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ROUTER_DNS_DEADLINE_FILE", str(tmp_path / "deadline"))
    calls = []

    class Done:
        returncode = 0
        stdout = "Router DNS set to 192.168.1.1"
        stderr = ""

    monkeypatch.setattr(
        router_dns.subprocess, "run", lambda *a, **k: (calls.append(a[0]), Done())[1]
    )
    _fake_session(monkeypatch, '{"pridns":"192.168.1.1","secdns":"192.168.1.1"}')
    resp = client.post("/api/router-dns/mode", json={"mode": "router"})
    assert resp.status_code == 200
    assert calls and calls[0][-1] == "off"
    assert resp.json()["mode"] == "router"


def _mock_switch(monkeypatch, calls):
    class Done:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr(
        router_dns.subprocess, "run", lambda *a, **k: (calls.append(a[0]), Done())[1]
    )


def test_max_hours_default_and_override(monkeypatch):
    monkeypatch.delenv("ROUTER_DNS_MAX_HOURS", raising=False)
    assert router_dns._max_hours() == 3.0
    monkeypatch.setenv("ROUTER_DNS_MAX_HOURS", "5")
    assert router_dns._max_hours() == 5.0
    monkeypatch.setenv("ROUTER_DNS_MAX_HOURS", "garbage")
    assert router_dns._max_hours() == 3.0


def test_deadline_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("ROUTER_DNS_DEADLINE_FILE", str(tmp_path / "deadline"))
    assert router_dns._read_deadline_epoch() is None
    router_dns._write_deadline(1_700_000_000)
    assert router_dns._read_deadline_epoch() == 1_700_000_000
    info = router_dns._deadline_info(now=1_700_000_000 - 3600)
    assert info["seconds_remaining"] == 3600
    assert info["enabled_at"] is not None and info["expires_at"] is not None
    router_dns._clear_deadline()
    assert router_dns._read_deadline_epoch() is None


def test_manual_on_writes_deadline_off_clears(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ROUTER_DNS_DEADLINE_FILE", str(tmp_path / "deadline"))
    monkeypatch.setenv("ROUTER_DNS_MAX_HOURS", "3")
    calls: list = []
    _mock_switch(monkeypatch, calls)

    _fake_session(monkeypatch, '{"pridns":"192.168.1.20","secdns":"192.168.1.20"}')
    resp = client.post("/api/router-dns/mode", json={"mode": "dnsmasq"})
    assert resp.status_code == 200
    assert calls and calls[0][-1] == "on"
    body = resp.json()
    assert body["mode"] == "dnsmasq"
    assert body["seconds_remaining"] is not None
    assert 0 < body["seconds_remaining"] <= 3 * 3600
    assert (tmp_path / "deadline").is_file()

    _fake_session(monkeypatch, '{"pridns":"192.168.1.1","secdns":"192.168.1.1"}')
    resp = client.post("/api/router-dns/mode", json={"mode": "router"})
    assert resp.status_code == 200
    assert not (tmp_path / "deadline").exists()
    assert resp.json()["seconds_remaining"] is None


def test_status_clears_stale_deadline(client, monkeypatch, tmp_path):
    monkeypatch.setenv("ROUTER_DNS_DEADLINE_FILE", str(tmp_path / "deadline"))
    (tmp_path / "deadline").write_text(f"{int(time.time()) + 3600}\n")
    # Router already on default while a deadline lingers (e.g. reverted
    # by hand in the router panel) → status drops the stale file.
    _fake_session(monkeypatch, '{"pridns":"192.168.1.1","secdns":"192.168.1.1"}')
    resp = client.get("/api/router-dns/status")
    assert resp.status_code == 200
    assert resp.json()["mode"] == "router"
    assert not (tmp_path / "deadline").exists()
