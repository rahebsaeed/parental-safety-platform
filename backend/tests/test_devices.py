from __future__ import annotations

from fastapi.testclient import TestClient


def test_list_devices(client: TestClient) -> None:
    response = client.get("/api/devices")
    assert response.status_code == 200
    devices = response.json()
    assert len(devices) == 3

    # Check dev_02 details
    dev_02 = next(d for d in devices if d["device_id"] == "dev_02")
    assert dev_02["friendly_name"] == "Kid Tablet"
    assert dev_02["device_type"] == "Android"
    assert dev_02["current_ip"] == "192.168.1.4"
    assert dev_02["query_count"] == 4
    assert dev_02["dns_visibility"] == "FULL"


def test_list_devices_filter_by_status(client: TestClient) -> None:
    response = client.get("/api/devices?status=offline")
    assert response.status_code == 200
    devices = response.json()
    assert len(devices) == 1
    assert devices[0]["device_id"] == "dev_03"


def test_get_device_detail(client: TestClient) -> None:
    response = client.get("/api/devices/dev_02")
    assert response.status_code == 200
    data = response.json()
    assert data["device_id"] == "dev_02"
    assert len(data["addresses"]) == 2
    assert data["addresses"][0]["ip_address"] == "192.168.1.4"
    assert len(data["status_events"]) == 1
    assert "youtube.com" in data["recent_domains"]
    assert "google.com" in data["recent_domains"]


def test_get_device_not_found(client: TestClient) -> None:
    response = client.get("/api/devices/nonexistent")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_update_device_rename_and_classify(client: TestClient) -> None:
    patch_payload = {
        "friendly_name": "Updated Tablet",
        "device_type": "Gaming Device",
    }
    response = client.patch("/api/devices/dev_02", json=patch_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["friendly_name"] == "Updated Tablet"
    assert data["device_type"] == "Gaming Device"

    # Verify persistence via GET
    get_res = client.get("/api/devices/dev_02")
    assert get_res.json()["friendly_name"] == "Updated Tablet"


def test_update_device_not_found(client: TestClient) -> None:
    response = client.patch(
        "/api/devices/nonexistent",
        json={"friendly_name": "Ghost"},
    )
    assert response.status_code == 404
