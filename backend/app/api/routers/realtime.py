from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse

from backend.app.services.realtime import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Real-Time Updates"])


@router.websocket("/ws")
async def websocket_updates(websocket: WebSocket) -> None:
    """
    WebSocket endpoint streaming live DNS activity, device status, and safety alerts.
    Clients receive real-time JSON event envelopes:
    {
      "type": "dns_activity" | "safety_alert" | "device_status" | "pong",
      "timestamp": "2026-09-13T00:45:00Z",
      "data": { ... }
    }
    """
    await manager.connect_socket(websocket)
    try:
        # Send initial handshake confirmation
        await websocket.send_text(
            json.dumps(
                {
                    "type": "connected",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": {"message": "Parental Safety Platform real-time stream connected"},
                }
            )
        )

        while True:
            text = await websocket.receive_text()
            try:
                msg = json.loads(text)
                if isinstance(msg, dict) and msg.get("type") == "ping":
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "pong",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "data": {},
                            }
                        )
                    )
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        await manager.disconnect_socket(websocket)
    except Exception as ex:
        logger.debug(f"WebSocket connection error: {ex}")
        await manager.disconnect_socket(websocket)


@router.get("/events")
async def sse_updates(request: Request) -> StreamingResponse:
    """
    Server-Sent Events (SSE) fallback stream for environments where WebSockets are restricted.
    Streams event lines with JSON data envelopes.
    """
    queue = manager.add_sse_queue()

    async def event_generator() -> AsyncGenerator[str, None]:
        # Initial greeting event
        greeting = {
            "type": "connected",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {"message": "Parental Safety Platform SSE stream connected"},
        }
        yield f"data: {json.dumps(greeting)}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Wait for next event or 15s heartbeat
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Send periodic SSE keep-alive comment
                    yield ": keep-alive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            manager.remove_sse_queue(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/realtime/status")
def get_realtime_status() -> dict:
    """Return active real-time subscriber counts."""
    return {
        "active_clients": manager.client_count,
        "websocket_clients": len(manager._active_sockets),
        "sse_subscribers": len(manager._sse_queues),
    }
