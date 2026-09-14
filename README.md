# Parental Safety Platform

A local-first network monitoring platform for home Wi-Fi networks: device
discovery, DNS/domain visibility, safety alerting, and behavior analytics —
without installing anything on the monitored devices, and without spyware
capabilities (no keylogging, message interception, webcam/mic capture,
screen capture, or credential theft — see `docs/architecture/phase-1-discovery.md`
for the full boundary).

## Status: All 12 Phases Complete ✅

The full system is built, deployed, and running in production on
Ubuntu `192.168.1.20` (`wlp0s20f3`, subnet `192.168.1.0/24`):

- **Phase 1** — Network discovery via ARP (active + passive) ✅
- **Phase 2** — DNS observation via dnsmasq ✅
- **Phase 3** — Device identity management (stable IDs, MAC randomization) ✅
- **Phase 4** — Domain classification & safety alerts (184 rules) ✅
- **Phase 5** — Privacy scoring (full/partial visibility) ✅
- **Phase 6** — Parental controls (pause, curfew, whitelist/blacklist) ✅
- **Phase 7** — Device activity & history ✅
- **Phase 8** — React dashboard (device cards, activity feed, privacy) ✅
- **Phase 9** — Real-time updates (WebSocket + SSE) ✅
- **Phase 10** — Security (parent password, rate limits, CSRF, audit log) ✅
- **Phase 11** — Systemd + nginx deployment (re-runnable install.sh) ✅
- **Phase 12** — Tailscale remote access + authentication + device matching fix ✅

See `docs/ROADMAP.md` for the full phase-by-phase plan, what's been
confirmed about this specific network, and a running incident log.

## Quickstart (run this on your actual Ubuntu machine)

```bash
# 1. Full production install (idempotent — safe to re-run):
bash infrastructure/scripts/install.sh

# 2. Verify it's running:
curl http://192.168.1.20/api/health
curl http://192.168.1.20/api/devices

# 3. Open the dashboard:
#    LAN:  http://192.168.1.20/
#    Tailnet: http://100.99.54.78/
```

## Repository layout

```text
parental-safety-platform/
├── backend/          FastAPI/SQLAlchemy API ✅
├── frontend/         React dashboard (dashboard-12) ✅
├── collector/        Device discovery + DNS collector ✅
├── infrastructure/   systemd units, nginx, install.sh ✅
├── docs/
│   ├── architecture  Discovery-phase writeup + phase plan
│   ├── networking    Reality-check procedure + limitations
│   ├── security      Threat model + controls
│   ├── api           API reference
│   └── deployment    Install & deployment docs
├── scripts/          One-off dev/ops scripts
└── tests/            Cross-component tests
```

## Authentication

The dashboard requires a parent password (configured during install
via the `PARENT_PASSWORD` env var in `.env`). Access routes (`/`,
`/dashboard`, `/privacy`, `/activity`, `/devices`, `/settings`)
are protected; the login page redirects unauthenticated users.

## Production services

| Service | Unit | Notes |
|---|---|---|
| DNS collector | `parental-monitor-collector` | dnsmasq + DNS ingestion |
| Device discovery | `parental-monitor-discovery` | Periodic ARP scan |
| API server | `parental-monitor-api` | FastAPI on `127.0.0.1:8000` |
| Web server | `nginx` | Serves React + proxies `/api` on port 80 |

Remote access via [Tailscale](https://tailscale.com) (`tailnet-root:200`).
No router port-forwards exist.

## Read next

1. `docs/ROADMAP.md` — status of all phases, network specifics, incident log
2. `docs/architecture/phase-1-discovery.md` — full architecture
3. `docs/networking/visibility-and-limitations.md` — what this system can and cannot see
4. `collector/README.md` — Phase 1 setup in more detail
