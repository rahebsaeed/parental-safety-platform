from __future__ import annotations

from fastapi.testclient import TestClient


def test_top_domains(client: TestClient) -> None:
    response = client.get("/api/domains/top")
    assert response.status_code == 200
    items = response.json()
    assert len(items) >= 3

    # youtube.com should be rank #1 (2 queries: A and AAAA)
    assert items[0]["domain"] == "youtube.com"
    assert items[0]["query_count"] == 2
    assert items[0]["unique_devices"] == 1


def test_top_domains_filter_by_device(client: TestClient) -> None:
    response = client.get("/api/domains/top?device_id=dev_02")
    assert response.status_code == 200
    items = response.json()
    domains = [i["domain"] for i in items]
    assert "bypassed-doh.com" not in domains  # belonged to NULL/dev_unknown


def test_dns_stats(client: TestClient) -> None:
    response = client.get("/api/dns/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["total_queries"] == 5
    assert data["full_visibility_queries"] == 4
    assert data["partial_visibility_queries"] == 1
    assert data["partial_percentage"] == 20.0
    assert data["unique_domains"] == 4
