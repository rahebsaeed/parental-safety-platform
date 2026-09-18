# Parental Safety Platform

A local-first network monitoring platform for home Wi-Fi networks: device
discovery, DNS/domain visibility, safety alerting, and behavior analytics —
without installing anything on the monitored devices, and without spyware
capabilities (no keylogging, message interception, webcam/mic capture,
screen capture, or credential theft — see `docs/architecture/phase-1-discovery.md`
for the full boundary).

## Status: All 18 Phases Complete ✅

The full system is built, deployed, and running in production on
Ubuntu `192.168.1.20` (`wlp0s20f3`, subnet `192.168.1.0/24`):

- **Phase 1** — Network discovery via ARP (active + passive) ✅
- **Phase 2** — DNS observation via dnsmasq ✅
- **Phase 3** — Device identity management (stable IDs, MAC randomization) ✅
- **Phase 4** — Domain classification & safety alerts (359 rules) ✅
- **Phase 5** — Privacy scoring (full/partial visibility) ✅
- **Phase 6** — Parental controls (pause, curfew, whitelist/blacklist) ✅
- **Phase 7** — Device activity & history ✅
- **Phase 8** — React dashboard (device cards, activity feed, privacy) ✅
- **Phase 9** — Real-time updates (WebSocket + SSE) ✅
- **Phase 10** — Security (parent password, rate limits, CSRF, audit log) ✅
- **Phase 11** — Systemd + nginx deployment (re-runnable install.sh) ✅
- **Phase 12** — Tailscale remote access + authentication + device matching fix ✅
- **Phase 13** — Password Change UI + On-Demand Scan ✅
- **Phase 14** — DNS Resolver Reliability ✅
- **Phase 15** — AI-assisted classification (OpenRouter free models → persisted rules) ✅
- **Phase 16** — Safe-DNS failover control (header badge + switch, suspend/shutdown automation) ✅
- **Phase 17** — Discovery hardening (router DHCP leases, DNS-driven placeholders, hourly scans) ✅
- **Phase 18** — Manual-only Safe-DNS + 3h failsafe + return-to-normal reset ✅

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
| DNS collector | `parental-monitor-collector` | dnsmasq tail + DNS ingestion |
| API server | `parental-monitor-api` | FastAPI on `127.0.0.1:8000` |
| Web server | `nginx` | Serves React + proxies `/api` on port 80 |
| Hourly discovery scan | `parental-monitor-scan.timer` | ARP + router DHCP leases, keeps IP→device mapping fresh |
| Hourly AI classification sync | `parental-monitor-ai-sync.timer` | Static rules, then top-20 unknowns to OpenRouter, persisted as rules |
| 3h Safe-DNS failsafe | `parental-monitor-dns-revert.timer` (every 5 min) | Reverts router DNS to default if filtered mode exceeds `ROUTER_DNS_MAX_HOURS` (default 3h). The ONLY automation allowed to touch router DNS |

Remote access via [Tailscale](https://tailscale.com) (`100.99.54.78`).
No router port-forwards exist.

## AI-assisted classification

Static rules (359 suffix/contains/regex entries) classify known domains
instantly. Anything they miss goes to a free OpenRouter model, and the
verdict is **persisted as a rule** — each unknown is an AI call exactly
once, then cached forever:

- Classifications page → sandbox **AI mode** (Ask AI + Save as rule) and
  per-row **Ask AI** buttons for UNCATEGORIZED domains; Sync runs the
  bulk AI pass and reports counts.
- Every alert **Scan** refreshes classifications first, so a new adult
  site is labeled `ADULT_CONTENT` *before* evaluation — it cannot slip
  through as UNCATEGORIZED. `UNSAFE`/`GAMBLING` verdicts map to
  `ADULT_CONTENT` (CRITICAL/HIGH alerts); manual overrides always win;
  `UNKNOWN` verdicts stay retryable.
- Free models rotate with per-model cooldowns when pools throttle
  (`Settings → OpenRouter` shows the serving model); batch calls are
  paced 5s apart. Key is entered in Settings, validated with Test, and
  stored in the `settings` DB table — never in `.env` or git.

## Router DNS control (manual-only + 3h failsafe)

Protection only works while the router advertises this PC (`192.168.1.20`)
as DNS. The header on every dashboard page shows the router's **actual**
reported DNS (green `rosa-PC` = filtered, amber `Router` = unfiltered)
with a one-click switch (`GET/POST /api/router-dns/*`) — switching asks
for confirmation first.

Switching is **manual only**: no boot/shutdown/suspend/WiFi hook touches
the router (they caused a WiFi-connected-but-no-internet outage and were
removed; re-running `install.sh` deletes any leftover copies). The sole
automation is a **3-hour failsafe** (`parental-monitor-dns-revert.timer`,
every 5 min): enabling filtered DNS starts a deadline
(`ROUTER_DNS_MAX_HOURS`, default 3), the header counts down to it, `+3h`
restarts the clock, and expiry flips the router back to `192.168.1.1`
automatically in case you forget it on.

If anything ever breaks networking, run the emergency reset (keeps your
database, password, and logs, removes only what the project added):

```bash
sudo bash infrastructure/scripts/reset-to-normal.sh --dry-run  # preview
sudo bash infrastructure/scripts/reset-to-normal.sh --yes      # apply
```

## Read next

1. `docs/ROADMAP.md` — status of all phases, network specifics, incident log
2. `docs/architecture/phase-1-discovery.md` — full architecture
3. `docs/networking/visibility-and-limitations.md` — what this system can and cannot see
4. `collector/README.md` — Phase 1 setup in more detail
