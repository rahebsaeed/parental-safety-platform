"""Tests for the Router DNS control API.

The status/switch endpoints must never 500 on router trouble (unreachable
-> mode="unreachable" / HTTP 502), must reject bad modes with 422, and
must delegate switching to the canonical router-dns.sh script.
"""
from __future__ import annotations

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


def test_switch_delegates_to_script(client, monkeypatch):
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
