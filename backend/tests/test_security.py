import json
import pytest
from fastapi.testclient import TestClient

from backend.app.core.auth import session_registry
from backend.app.core.security_middleware import rate_limiter
from backend.app.main import app


@pytest.fixture(autouse=True)
def clean_security_state():
    """Reset rate limiter and active sessions before each test."""
    rate_limiter.clear()
    session_registry.clear()
    yield
    rate_limiter.clear()
    session_registry.clear()


def test_security_headers_present(client: TestClient):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert "strict-origin" in response.headers.get("Referrer-Policy", "")


def test_login_success(client: TestClient):
    response = client.post("/api/auth/login", json={"password": "admin123"})
    assert response.status_code == 200
    data = response.json()
    assert data["authenticated"] is True
    assert "token" in data
    assert "parent_session" in response.cookies


def test_login_failure_invalid_password(client: TestClient):
    response = client.post("/api/auth/login", json={"password": "wrongpassword"})
    assert response.status_code == 401
    assert "Invalid parent password" in response.json()["detail"]


def test_login_rate_limiting(client: TestClient):
    # Send 5 allowed attempts
    for _ in range(5):
        resp = client.post("/api/auth/login", json={"password": "wrong"})
        assert resp.status_code == 401

    # 6th attempt should be blocked with 429
    blocked = client.post("/api/auth/login", json={"password": "wrong"})
    assert blocked.status_code == 429
    assert blocked.headers.get("Retry-After") == "60"
    assert "Rate limit exceeded" in blocked.json()["detail"]


def test_auth_status_workflow(client: TestClient):
    # Initially not authenticated
    status_resp = client.get("/api/auth/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["authenticated"] is False

    # Log in
    login_resp = client.post("/api/auth/login", json={"password": "admin123"})
    token = login_resp.json()["token"]

    # Status with Bearer token
    status_authed = client.get("/api/auth/status", headers={"Authorization": f"Bearer {token}"})
    assert status_authed.status_code == 200
    assert status_authed.json()["authenticated"] is True

    # Logout
    logout_resp = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout_resp.status_code == 200

    # Status after logout
    status_after = client.get("/api/auth/status", headers={"Authorization": f"Bearer {token}"})
    assert status_after.json()["authenticated"] is False


def test_csrf_origin_check_blocks_malicious_origin(client: TestClient):
    # Cross-origin request from an untrusted external domain
    response = client.post(
        "/api/auth/login",
        json={"password": "admin123"},
        headers={"Origin": "https://evil-hacker-site.com"},
    )
    assert response.status_code == 403
    assert "Cross-origin state mutation rejected" in response.json()["detail"]


def test_audit_log_endpoint(client: TestClient):
    # Trigger a login to generate an audit log entry
    client.post("/api/auth/login", json={"password": "admin123"})

    audit_resp = client.get("/api/auth/audit")
    assert audit_resp.status_code == 200
    entries = audit_resp.json()
    assert len(entries) > 0
    actions = [e["action"] for e in entries]
    assert "AUTH_LOGIN_SUCCESS" in actions


def test_device_update_creates_audit_log(client: TestClient):
    # Rename dev_02
    resp = client.patch("/api/devices/dev_02", json={"friendly_name": "Kid Laptop", "device_type": "Laptop"})
    assert resp.status_code == 200

    audit_resp = client.get("/api/auth/audit?action=DEVICE_UPDATE")
    assert audit_resp.status_code == 200
    entries = audit_resp.json()
    assert len(entries) > 0
    assert entries[0]["target"] == "dev_02"
    assert "Kid Laptop" in entries[0]["details"]
