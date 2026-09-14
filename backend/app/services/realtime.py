from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Set

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from backend.app.db.session import SessionLocal
from backend.app.models.dns import DnsQuery
from backend.app.models.alert import SafetyAlert
from backend.app.models.device import DeviceStatusEvent

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket and SSE client connections."""

    def __init__(self) -> None:
        self._active_sockets: Set[WebSocket] = set()
        self._sse_queues: Set[asyncio.Queue] = set()
        self._lock = asyncio.Lock()

    async def connect_socket(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._active_sockets.add(websocket)
        logger.info(f"WebSocket client connected. Total active sockets: {len(self._active_sockets)}")

    async def disconnect_socket(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._active_sockets.discard(websocket)
        logger.info(f"WebSocket client disconnected. Total active sockets: {len(self._active_sockets)}")

    def add_sse_queue(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._sse_queues.add(q)
        logger.info(f"SSE client connected. Total SSE subscribers: {len(self._sse_queues)}")
        return q

    def remove_sse_queue(self, q: asyncio.Queue) -> None:
        self._sse_queues.discard(q)
        logger.info(f"SSE client disconnected. Total SSE subscribers: {len(self._sse_queues)}")

    async def broadcast(self, event_type: str, data: Dict[str, Any]) -> None:
        """Broadcast an event to all WebSocket and SSE clients."""
        payload = {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
        }
        text_data = json.dumps(payload)

        # Broadcast to WebSockets
        dead_sockets: List[WebSocket] = []
        async with self._lock:
            for ws in list(self._active_sockets):
                try:
                    await ws.send_text(text_data)
                except Exception as ex:
                    logger.debug(f"Failed to send to WebSocket {ws}: {ex}")
                    dead_sockets.append(ws)

            for dead_ws in dead_sockets:
                self._active_sockets.discard(dead_ws)

        # Broadcast to SSE queues
        dead_queues: List[asyncio.Queue] = []
        for q in list(self._sse_queues):
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                logger.warning("SSE queue full, dropping subscriber")
                dead_queues.append(q)
            except Exception:
                dead_queues.append(q)

        for dead_q in dead_queues:
            self._sse_queues.discard(dead_q)

    @property
    def client_count(self) -> int:
        return len(self._active_sockets) + len(self._sse_queues)


manager = ConnectionManager()


class SqliteChangeWatcher:
    """Watches SQLite database for newly inserted DNS queries, alerts, and device status events."""

    def __init__(self, connection_manager: ConnectionManager, poll_interval: float = 1.0) -> None:
        self.manager = connection_manager
        self.poll_interval = poll_interval
        self._last_dns_id: int | None = None
        self._last_alert_id: int | None = None
        self._last_status_event_id: int | None = None
        self._running = False
        self._task: asyncio.Task | None = None

    def initialize_watermarks(self, session: Session) -> None:
        """Initialize high-water marks from current database state."""
        max_dns = session.scalar(select(DnsQuery.id).order_by(desc(DnsQuery.id)).limit(1))
        self._last_dns_id = max_dns or 0

        max_alert = session.scalar(select(SafetyAlert.id).order_by(desc(SafetyAlert.id)).limit(1))
        self._last_alert_id = max_alert or 0

        max_event = session.scalar(select(DeviceStatusEvent.id).order_by(desc(DeviceStatusEvent.id)).limit(1))
        self._last_status_event_id = max_event or 0

        logger.info(
            f"SqliteChangeWatcher initialized with watermarks: "
            f"dns_id={self._last_dns_id}, alert_id={self._last_alert_id}, event_id={self._last_status_event_id}"
        )

    async def poll_once(self) -> None:
        """Poll SQLite for any records inserted since the last watermark."""
        try:
            with SessionLocal() as session:
                if self._last_dns_id is None:
                    self.initialize_watermarks(session)
                    return

                # Check new DNS queries
                new_queries = session.scalars(
                    select(DnsQuery)
                    .where(DnsQuery.id > self._last_dns_id)
                    .order_by(DnsQuery.id.asc())
                    .limit(50)
                ).all()

                for query in new_queries:
                    self._last_dns_id = query.id
                    await self.manager.broadcast(
                        "dns_activity",
                        {
                            "id": query.id,
                            "occurred_at": str(query.occurred_at) if query.occurred_at else None,
                            "source_ip": query.source_ip,
                            "device_id": query.device_id,
                            "domain": query.domain,
                            "query_type": query.query_type,
                            "response_status": query.response_status,
                            "dns_visibility": query.dns_visibility,
                        },
                    )

                # Check new safety alerts
                new_alerts = session.scalars(
                    select(SafetyAlert)
                    .where(SafetyAlert.id > self._last_alert_id)
                    .order_by(SafetyAlert.id.asc())
                    .limit(20)
                ).all()

                for alert in new_alerts:
                    self._last_alert_id = alert.id
                    await self.manager.broadcast(
                        "safety_alert",
                        {
                            "id": alert.id,
                            "device_id": alert.device_id,
                            "domain": alert.domain,
                            "alert_type": alert.alert_type,
                            "severity": alert.severity,
                            "title": alert.title,
                            "description": alert.description,
                            "rule_matched": alert.rule_matched,
                            "status": alert.status,
                            "occurrence_count": alert.occurrence_count,
                            "created_at": str(alert.created_at) if alert.created_at else None,
                        },
                    )

                # Check new device status events
                new_events = session.scalars(
                    select(DeviceStatusEvent)
                    .where(DeviceStatusEvent.id > self._last_status_event_id)
                    .order_by(DeviceStatusEvent.id.asc())
                    .limit(20)
                ).all()

                for evt in new_events:
                    self._last_status_event_id = evt.id
                    await self.manager.broadcast(
                        "device_status",
                        {
                            "id": evt.id,
                            "device_id": evt.device_id,
                            "status": evt.status,
                            "occurred_at": str(evt.occurred_at) if evt.occurred_at else None,
                        },
                    )

        except Exception as ex:
            logger.error(f"Error during SQLite change watcher poll: {ex}", exc_info=True)

    async def _run_loop(self) -> None:
        while self._running:
            try:
                # Only poll if there are active subscribers
                if self.manager.client_count > 0:
                    await self.poll_once()
                await asyncio.sleep(self.poll_interval)
            except asyncio.CancelledError:
                break
            except Exception as ex:
                logger.error(f"Change watcher loop encountered error: {ex}")
                await asyncio.sleep(self.poll_interval)

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("SqliteChangeWatcher background polling task started.")

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("SqliteChangeWatcher background polling task stopped.")


watcher = SqliteChangeWatcher(manager)
