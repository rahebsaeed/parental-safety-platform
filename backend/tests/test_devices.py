from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from backend.app.db import repository


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


def _freshen_seen(test_db, *device_ids: str) -> None:
    """Make fixture devices effectively online (seed last_seen is stale)."""
    now = datetime.now(timezone.utc).isoformat()
    for device_id in device_ids:
        test_db.execute(
            "UPDATE devices SET status='online', last_seen=? WHERE device_id=?",
            (now, device_id),
        )
    test_db.commit()


def test_online_excludes_gateway_but_all_keeps_it(
    client: TestClient, test_db, monkeypatch
) -> None:
    """The router never counts itself among connected clients — the online
    view must not either, while the full inventory keeps the gateway row
    (flagged) for DNS attribution."""
    _freshen_seen(test_db, "dev_01", "dev_02")
    monkeypatch.setattr(repository, "_detect_gateway_ip", lambda: "192.168.1.1")

    online = client.get("/api/devices?status=online").json()
    online_ids = [d["device_id"] for d in online]
    assert "dev_02" in online_ids
    assert "dev_01" not in online_ids

    everything = client.get("/api/devices").json()
    gateway = next(d for d in everything if d["device_id"] == "dev_01")
    assert gateway["is_gateway"] is True
    phone = next(d for d in everything if d["device_id"] == "dev_02")
    assert phone["is_gateway"] is False

    detail = client.get("/api/devices/dev_01").json()
    assert detail["is_gateway"] is True


def test_online_unchanged_when_gateway_undetectable(
    client: TestClient, test_db, monkeypatch
) -> None:
    """If gateway detection fails (CI box, no route), nothing is excluded."""
    _freshen_seen(test_db, "dev_01", "dev_02")
    monkeypatch.setattr(repository, "_detect_gateway_ip", lambda: None)

    online_ids = [d["device_id"] for d in client.get("/api/devices?status=online").json()]
    assert "dev_01" in online_ids
    assert "dev_02" in online_ids
