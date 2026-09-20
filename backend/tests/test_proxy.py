"""Tests for Phase 19 — web proxy observation API."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _seed_proxy(test_db) -> None:
    test_db.execute(
        "INSERT INTO proxy_requests (occurred_at, client_ip, device_id, method,"
        " scheme, host, port, path, full_url, user_agent, status_code,"
        " resp_content_type, resp_size, page_title, intercepted)"
        " VALUES ('2026-09-19 07:00:00', '192.168.1.8', 'dev_02', 'GET', 'https',"
        " 'www.google.com', 443, '/search?q=hello',"
        " 'https://www.google.com/search?q=hello', 'TestBrowser', 200,"
        " 'text/html', 1234, 'hello - Google Search', 1)"
    )
    test_db.execute(
        "INSERT INTO proxy_search_terms (occurred_at, device_id, engine,"
        " keywords, full_url)"
        " VALUES ('2026-09-19 07:00:00', 'dev_02', 'Google', 'hello',"
        " 'https://www.google.com/search?q=hello')"
    )
    test_db.commit()


def test_list_proxy_requests(client: TestClient, test_db) -> None:
    _seed_proxy(test_db)
    resp = client.get("/api/proxy/requests")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    item = data["items"][0]
    assert item["host"] == "www.google.com"
    assert item["page_title"] == "hello - Google Search"
    assert item["device_name"] == "Kid Tablet"
    assert "cookie" not in resp.text.lower()


def test_proxy_requests_filters(client: TestClient, test_db) -> None:
    _seed_proxy(test_db)
    assert client.get("/api/proxy/requests?method=POST").json()["total"] == 0
    assert client.get("/api/proxy/requests?domain=nope").json()["total"] == 0
    assert client.get("/api/proxy/requests?domain=google").json()["total"] == 1


def test_list_proxy_searches(client: TestClient, test_db) -> None:
    _seed_proxy(test_db)
    resp = client.get("/api/proxy/searches")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["engine"] == "Google"
    assert rows[0]["keywords"] == "hello"
    assert rows[0]["device_name"] == "Kid Tablet"


def test_hide_local_filters_infrastructure(client: TestClient, test_db) -> None:
    test_db.execute(
        "INSERT INTO proxy_requests (occurred_at, client_ip, method, scheme,"
        " host, port, path, full_url) VALUES"
        " ('2026-09-19 07:00:00', '192.168.1.20', 'GET', 'http',"
        " '192.168.1.1', 80, '/', 'http://192.168.1.1/'),"
        " ('2026-09-19 07:00:01', '192.168.1.20', 'GET', 'https',"
        " 'www.google.com', 443, '/', 'https://www.google.com/')"
    )
    test_db.commit()
    hidden = client.get("/api/proxy/requests").json()
    assert all(r["host"] != "192.168.1.1" for r in hidden["items"])
    assert any(r["host"] == "www.google.com" for r in hidden["items"])
    shown = client.get("/api/proxy/requests?hide_local=false").json()
    assert any(r["host"] == "192.168.1.1" for r in shown["items"])


def test_proxy_coverage_flags_unsupervised(client: TestClient, test_db) -> None:
    test_db.execute(
        "INSERT INTO dns_queries (occurred_at, source_ip, device_id, domain,"
        " query_type, response_status, dns_visibility)"
        " VALUES ('2026-09-19 07:00:00', '192.168.1.4', 'dev_02', 'example.com',"
        " 'A', 'NOERROR', 'FULL')"
    )
    test_db.commit()
    resp = client.get("/api/proxy/coverage?days=90")
    assert resp.status_code == 200
    by_id = {d["device_id"]: d for d in resp.json()["devices"]}
    # dev_02 has DNS but no proxy rows → DNS-only; dev_01 has neither.
    assert by_id["dev_02"]["dns_queries"] >= 1
    assert by_id["dev_02"]["has_proxy"] is False
    assert by_id["dev_01"]["device_name"] == "Router Gateway"


def test_proxy_ca_missing_is_404(client: TestClient, monkeypatch) -> None:
    import backend.app.api.routers.proxy as proxy_mod

    monkeypatch.setattr(proxy_mod, "CA_DIR", proxy_mod.Path("/nonexistent-ca-dir"))
    resp = client.get("/api/proxy/ca.pem")
    assert resp.status_code == 404
