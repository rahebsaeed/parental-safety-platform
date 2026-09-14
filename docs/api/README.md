# Parental Safety Platform — API Documentation

The REST API is implemented in FastAPI and documented interactively via OpenAPI/Swagger.

## OpenAPI Documentation

When the backend API server is running:
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **OpenAPI Schema (JSON)**: `http://localhost:8000/openapi.json`

In production the API sits behind nginx at `http://192.168.1.20/api/`
(uvicorn itself binds loopback-only `127.0.0.1:8000`).

## Architecture & Endpoint Reference

Full service specification: [docs/architecture/phase-3-backend-api.md](../architecture/phase-3-backend-api.md)

### Devices & discovery

| Method & path | Purpose |
|---|---|
| `GET /api/devices[?status=]` | Discovered devices with IP/MAC/visibility |
| `GET /api/devices/{id}` | Detail: address history, top domains |
| `PATCH /api/devices/{id}` | Rename / reclassify |
| `POST /api/devices/scan` | Trigger a discovery scan now |

### DNS activity

| Method & path | Purpose |
|---|---|
| `GET /api/activity?...` | **Paginated**: `{total, limit, offset, items[]}` — never a bare array; clients must read `.items` |

### Classifications (static rules + AI)

| Method & path | Purpose |
|---|---|
| `GET /api/classifications/domains` | Stored rules, filterable by category |
| `GET /api/classifications/domains/{domain}` | Stored row, else live rule evaluation (no write) |
| `POST /api/classifications/classify` | Rule evaluation only, no DB write |
| `POST /api/classifications/sync[?ai=&ai_limit=]` | Rule-sync all unseen domains, then bounded AI pass over top UNCATEGORIZED by volume |
| `POST /api/classifications/ai-sync?limit=` | Dedicated AI pass over top UNCATEGORIZED domains |
| `POST /api/classifications/ai-classify/{domain}` | AI-classify one domain and persist as a rule (rules tried first, overrides never touched) |
| `PUT /api/classifications/domains/{domain}/override` | Manual parent override (sacred: automation never overwrites) |

AI verdicts map onto rule categories (`UNSAFE`/`GAMBLING` → `ADULT_CONTENT`,
`MESSAGING` → `SOCIAL_MEDIA`, …); `UNKNOWN` is never persisted. See
`backend/app/classifiers/openrouter_classifier.py`.

### Safety alerts

| Method & path | Purpose |
|---|---|
| `GET /api/alerts`, `GET /api/alerts/summary` | List / aggregate alerts |
| `POST /api/alerts/scan[?ai=&ai_limit=]` | Refresh classifications first, then evaluate (an unlisted adult site is labeled *before* it can slip through) |
| `GET/PATCH /api/alerts/{id}` | Detail / triage status |

### Analytics & domain security

| Method & path | Purpose |
|---|---|
| `GET /api/analytics/*` | Overview, categories, active-hours, timeline, export |
| `GET /api/domains/security|dangerous|subjects` | Keyword baseline overridden by stored rules (AI/reviewed verdicts win; `ADULT_CONTENT` → Dangerous) |

### Router DNS failover

| Method & path | Purpose |
|---|---|
| `GET /api/router-dns/status` | Router-reported DNS (`mode`: `dnsmasq`/`router`/`custom`/`unknown`/`unreachable`) |
| `POST /api/router-dns/mode` | `{"mode":"dnsmasq"\|"router"}` — delegates to `scripts/router-dns.sh` |

### OpenRouter AI

| Method & path | Purpose |
|---|---|
| `GET /api/openrouter/categories` | Model taxonomy |
| `GET /api/openrouter/classify/{domain}[?force]` | Single verdict (cache-aware) |
| `POST /api/openrouter/classify-batch` | `{domains:[...]}` — paced 5s apart, per-model cooldown rotation |
| `GET /api/openrouter/api-key-status` | Key configured? + per-model health (`cooling`, `retry_in`) |
| `POST /api/openrouter/api-key` | Save key (`{"key":"..."}`) |
| `POST /api/openrouter/api-key/test` | Validate without saving (or validate saved) |
| `GET /api/openrouter/top-domains-by-category` | Top domains grouped by cached AI verdict |

### Auth & realtime

| Method & path | Purpose |
|---|---|
| `POST /api/auth/login|logout`, `GET /api/auth/status`, `POST /api/auth/change-password` | Parent sessions (`PARENT_PASSWORD`) |
| `WS /api/ws`, `GET /api/events`, `GET /api/realtime/status` | WebSocket + SSE fallback streams |
