# Phase 9 — Real-Time Updates Architecture (WebSockets & SSE)

## 1. Overview & Objective
Phase 9 delivers real-time event streaming between the local observation collector, the FastAPI backend, and the Phase 8 React dashboard. 

Rather than requiring periodic polling loops or manual dashboard refreshes, incoming events (`dns_activity`, `safety_alert`, and `device_status`) are broadcast immediately over a persistent **WebSocket** connection (with automatic fallback to **Server-Sent Events** / SSE).

---

## 2. Technical Stack & Component Topology

```
┌─────────────────────────────────────────────────────────────┐
│                    Network & DNS Ingestion                  │
│   dnsmasq (192.168.1.20:53) ──> dnsmasq.log ──> Ingester   │
└──────────────────────────────┬──────────────────────────────┘
                               │ SQLite Inserts
                               ▼
┌─────────────────────────────────────────────────────────────┐
│              discovery.sqlite3 (WAL Mode)                   │
│   dns_queries  |  safety_alerts  |  device_status_events    │
└──────────────────────────────┬──────────────────────────────┘
                               │ High-watermark polling
                               ▼
┌─────────────────────────────────────────────────────────────┐
│               SqliteChangeWatcher (FastAPI)                 │
│   Polls new query/alert/device IDs with sub-second latency  │
└──────────────────────────────┬──────────────────────────────┘
                               │ Event Broadcast
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                     ConnectionManager                       │
│   Active WebSockets: Set[WebSocket]                         │
│   SSE Subscribers:   Set[asyncio.Queue]                     │
└──────────────────────────────┬──────────────────────────────┘
                               │
            ┌──────────────────┴──────────────────┐
            │ ws://.../api/ws                     │ http://.../api/events
            ▼                                     ▼
┌─────────────────────────────────────────────────────────────┐
│             React 19 Dashboard (useRealtime Hook)           │
│   - Header Live Stream Pulse Indicator                      │
│   - Activity Stream: Prepends live DNS queries              │
│   - Safety Console: Real-time alert badges and banners      │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Event Envelope Format
All streamed events follow a standardized JSON envelope structure:

```json
{
  "type": "dns_activity" | "safety_alert" | "device_status" | "connected" | "pong",
  "timestamp": "2026-09-13T00:50:00.000Z",
  "data": { ... }
}
```

### Event Payloads
- **`dns_activity`**:
  ```json
  {
    "id": 1104,
    "occurred_at": "2026-09-13T00:49:58Z",
    "source_ip": "192.168.1.4",
    "device_id": "dev_03",
    "domain": "connectivitycheck.gstatic.com",
    "query_type": "AAAA",
    "response_status": "NOERROR",
    "dns_visibility": "FULL"
  }
  ```
- **`safety_alert`**:
  ```json
  {
    "id": 24,
    "device_id": "dev_03",
    "domain": "suspicious-login-apple.com",
    "alert_type": "PHISHING_SUSPICIOUS",
    "severity": "HIGH",
    "title": "Phishing or Impersonation Lure",
    "description": "Suspicious brand impersonation pattern detected.",
    "rule_matched": "KEYWORD_REGEX",
    "status": "ACTIVE",
    "occurrence_count": 1
  }
  ```
- **`device_status`**:
  ```json
  {
    "id": 14,
    "device_id": "dev_03",
    "status": "online",
    "occurred_at": "2026-09-13T00:49:58Z"
  }
  ```

---

## 4. Dual Transport Support

1. **Primary Transport — WebSocket (`/api/ws`)**:
   - Bi-directional framing with zero HTTP overhead.
   - Client sends heartbeat `{"type": "ping"}`; server replies `{"type": "pong"}`.
   - Vite dev proxy configured with `ws: true` for development.
2. **Fallback Transport — Server-Sent Events (`/api/events`)**:
   - HTTP/1.1 `text/event-stream` with standard chunked transfers.
   - Automatic 15-second `: keep-alive` comments to prevent proxy socket timeout.

---

## 5. Frontend Integration (`useRealtime`)

- Automatic reconnection with exponential backoff (`1s`, `1.5s`, ..., up to `10s`).
- In `Header.tsx`: Real-time badge dynamically displays `WebSocket Live` with accent pulse.
- In `ActivityPage.tsx`: Live queries prepend directly into table without page reload.
- In `AlertsPage.tsx` & `App.tsx`: Unacknowledged alert badge and alert lists update automatically when new threats or bypasses are flagged.

---

## 6. Verification & Automated Testing
- **`backend/tests/test_realtime.py`**:
  - `test_realtime_status_endpoint`: Status endpoint schema verification.
  - `test_websocket_connect_and_handshake`: Handshake protocol validation.
  - `test_websocket_ping_pong`: Bi-directional ping/pong verification.
  - `test_sse_subscriber_queue_lifecycle`: Queue memory leak prevention.
  - `test_manager_broadcast_to_websocket`: Broadcast distribution.
  - `test_sqlite_change_watcher_broadcast`: SQLite watermark change detection.
- Full test suites: 103 backend + 133 collector = **236 passing tests**.
