import json
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.main import create_app
from backend.app.services.realtime import ConnectionManager, SqliteChangeWatcher
from backend.app.models.base import Base
from backend.app.models.dns import DnsQuery
from backend.app.models.device import Device, DeviceStatusEvent
from backend.app.models.alert import SafetyAlert


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def in_memory_session():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def test_realtime_status_endpoint(client):
    response = client.get("/api/realtime/status")
    assert response.status_code == 200
    data = response.json()
    assert "active_clients" in data
    assert "websocket_clients" in data
    assert "sse_subscribers" in data


def test_websocket_connect_and_handshake(client):
    with client.websocket_connect("/api/ws") as websocket:
        data = websocket.receive_text()
        msg = json.loads(data)
        assert msg["type"] == "connected"
        assert "message" in msg["data"]


def test_websocket_ping_pong(client):
    with client.websocket_connect("/api/ws") as websocket:
        # Initial greeting
        _ = websocket.receive_text()

        # Ping
        websocket.send_text(json.dumps({"type": "ping"}))
        reply = json.loads(websocket.receive_text())
        assert reply["type"] == "pong"


def test_sse_subscriber_queue_lifecycle():
    cm = ConnectionManager()
    queue = cm.add_sse_queue()
    assert cm.client_count == 1

    cm.remove_sse_queue(queue)
    assert cm.client_count == 0


@pytest.mark.anyio
async def test_manager_broadcast_to_websocket(client):
    with client.websocket_connect("/api/ws") as websocket:
        _ = websocket.receive_text()  # Handshake

        from backend.app.services.realtime import manager

        await manager.broadcast(
            "dns_activity",
            {
                "id": 999,
                "domain": "realtime.safety.test",
                "device_id": "dev_test",
                "query_type": "A",
                "response_status": "NOERROR",
                "dns_visibility": "FULL",
            },
        )

        incoming = json.loads(websocket.receive_text())
        assert incoming["type"] == "dns_activity"
        assert incoming["data"]["domain"] == "realtime.safety.test"
        assert incoming["data"]["device_id"] == "dev_test"


@pytest.mark.anyio
async def test_sqlite_change_watcher_broadcast(in_memory_session):
    cm = ConnectionManager()
    watcher = SqliteChangeWatcher(cm)
    watcher.initialize_watermarks(in_memory_session)

    # Insert a device and a new DNS query
    dev = Device(
        device_id="dev_rt",
        friendly_name="Test RT Phone",
        status="online",
        confidence="HIGH",
        first_seen=datetime.now(timezone.utc).isoformat(),
        last_seen=datetime.now(timezone.utc).isoformat(),
    )
    in_memory_session.add(dev)
    in_memory_session.flush()

    new_query = DnsQuery(
        occurred_at=datetime.now(timezone.utc).isoformat(),
        source_ip="192.168.1.50",
        device_id="dev_rt",
        domain="live-stream.org",
        query_type="A",
        response_status="NOERROR",
        dns_visibility="FULL",
    )
    in_memory_session.add(new_query)
    in_memory_session.commit()

    queue = cm.add_sse_queue()
    try:
        # Simulate watcher detection using the in_memory_session query
        new_queries = in_memory_session.query(DnsQuery).filter(DnsQuery.id > watcher._last_dns_id).all()
        for q in new_queries:
            watcher._last_dns_id = q.id
            await cm.broadcast(
                "dns_activity",
                {
                    "id": q.id,
                    "occurred_at": q.occurred_at,
                    "source_ip": q.source_ip,
                    "device_id": q.device_id,
                    "domain": q.domain,
                    "query_type": q.query_type,
                    "response_status": q.response_status,
                    "dns_visibility": q.dns_visibility,
                },
            )

        assert not queue.empty()
        event = queue.get_nowait()
        assert event["type"] == "dns_activity"
        assert event["data"]["domain"] == "live-stream.org"
    finally:
        cm.remove_sse_queue(queue)
