from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_activity_all(client: TestClient) -> None:
    response = client.get("/api/activity")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 5
    assert data["limit"] == 50
    assert data["offset"] == 0

    # Ensure device_name joined properly
    item_dev_02 = next(i for i in data["items"] if i["device_id"] == "dev_02")
    assert item_dev_02["device_name"] == "Kid Tablet"


def test_list_activity_pagination(client: TestClient) -> None:
    response = client.get("/api/activity?limit=2&offset=1")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 1


def test_list_activity_filter_device_id(client: TestClient) -> None:
    response = client.get("/api/activity?device_id=dev_02")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4
    assert all(i["device_id"] == "dev_02" for i in data["items"])


def test_list_activity_filter_domain_substring(client: TestClient) -> None:
    response = client.get("/api/activity?domain=tube")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert all("youtube.com" in i["domain"] for i in data["items"])


def test_list_activity_filter_visibility(client: TestClient) -> None:
    response = client.get("/api/activity?visibility=PARTIAL")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["domain"] == "bypassed-doh.com"
    assert data["items"][0]["dns_visibility"] == "PARTIAL"


def test_list_activity_filter_response_status(client: TestClient) -> None:
    response = client.get("/api/activity?response_status=NXDOMAIN")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["domain"] == "badtracker.evil"


def test_query_types_endpoint(client: TestClient) -> None:
    response = client.get("/api/activity/types")
    assert response.status_code == 200
    types = {row["query_type"] for row in response.json()}
    assert {"A", "AAAA"} <= types


def test_activity_items_carry_category_and_tags(client: TestClient, test_db) -> None:
    test_db.execute(
        "INSERT INTO domain_classifications (domain, category) VALUES"
        " ('youtube.com', 'STREAMING_VIDEO')"
    )
    test_db.commit()
    response = client.get("/api/activity?domain=youtube.com&limit=1")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["category"] == "STREAMING_VIDEO"
    assert isinstance(item["tags"], list)
