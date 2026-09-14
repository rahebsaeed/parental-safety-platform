# Phase 3 — Backend API Architecture

## Summary

Phase 3 implements the platform's REST API layer using **FastAPI + Pydantic v2**.

The API connects directly to the existing SQLite database populated by Phase 1 (device discovery) and Phase 2 (DNS observation), exposing structured REST endpoints for frontend consumption and automated inspection.

---

## Service Overview

- **Port**: `8000` (`http://0.0.0.0:8000`)
- **Interactive Documentation**:
  - Swagger UI: `http://localhost:8000/docs`
  - ReDoc: `http://localhost:8000/redoc`
- **CORS**: Enabled for local development (supports React/Vite frontends on port 3000/5173).
- **Database Access**: Safe concurrent access to `discovery.sqlite3` with `PRAGMA journal_mode=WAL` and `PRAGMA busy_timeout=5000`.

---

## Endpoint Reference

### 1. Health & Status
- **`GET /health`** or **`GET /api/health`**
  - Returns overall system health, database connection state, device count, query count, and daemon liveness (dnsmasq & DNS ingester).
  ```json
  {
    "status": "healthy",
    "database_connected": true,
    "database_path": "/path/to/discovery.sqlite3",
    "devices_count": 6,
    "dns_queries_count": 342,
    "dnsmasq_running": true,
    "ingester_running": true
  }
  ```

### 2. Devices
- **`GET /api/devices`**
  - Query parameters: `status` (`online` | `offline`)
  - Returns all network devices with current IP, MAC, friendly name, device type, query volume, and DNS visibility status (`FULL`, `PARTIAL`, `NONE`).
- **`GET /api/devices/{device_id}`**
  - Returns device profile, full IP/MAC address observation history, status transition log, and recent distinct domains visited.
- **`PATCH /api/devices/{device_id}`**
  - Request body:
    ```json
    {
      "friendly_name": "Kid Phone",
      "device_type": "Android"
    }
    ```
  - Renames or reclassifies the device in the database (matches CLI `rename` / `classify`).

### 3. DNS Activity Stream
- **`GET /api/activity`**
  - Paginated real-time DNS query feed.
  - Query parameters:
    - `device_id`: Filter queries for a specific device (e.g. `dev_03`)
    - `domain`: Substring search on domain name (e.g. `youtube`)
    - `query_type`: Filter by record type (`A`, `AAAA`, `HTTPS`, etc.)
    - `response_status`: Filter by status (`NOERROR`, `NXDOMAIN`, etc.)
    - `visibility`: `FULL` (attributed to device) or `PARTIAL` (bypassed/unattributed)
    - `limit`: Records per page (default: 50, max: 500)
    - `offset`: Pagination offset (default: 0)

### 4. Domain Analytics & Visibility Stats
- **`GET /api/domains/top`**
  - Query parameters: `device_id`, `limit` (default: 20)
  - Returns most-frequently queried domains ordered by volume, including count of distinct devices querying each domain.
- **`GET /api/dns/stats`**
  - Returns overall DNS observation health: total queries, full visibility count, partial visibility count, bypass percentage (DoH/DoT suspicion indicator), and unique domains observed.

---

## How to Run

Activate the platform virtual environment:

```bash
source collector/.venv/bin/activate
```

Start the API server:
```bash
parental-api start
```

Or using `uvicorn` directly:
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Verification & Testing

Run all backend unit tests:
```bash
python -m pytest backend/tests/ -v
```

Run all collector discovery and ingester tests:
```bash
python -m pytest collector/tests/ -q
```
