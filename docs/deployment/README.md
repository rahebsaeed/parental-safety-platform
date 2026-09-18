# Deployment

Production lives at `/opt/parental-safety` on Ubuntu, installed by the
idempotent `infrastructure/scripts/install.sh` (safe to re-run: it copies
units, `daemon-reload`s, and enables everything).

## Systemd units

| Unit | Type | Schedule / trigger | Purpose |
|---|---|---|---|
| `parental-monitor-collector` | service | always-on | dnsmasq log tail + DNS ingestion |
| `parental-monitor-api` | service | always-on | FastAPI on `127.0.0.1:8000` |
| `dnsmasq` | service | always-on | LAN resolver on port 53, `log-queries` on |
| `parental-monitor-scan.service` | oneshot | `parental-monitor-scan.timer` hourly (+5m jitter, persistent) | ARP + router-DHCP discovery; keeps IP→device mapping fresh |
| `parental-monitor-ai-sync.service` | oneshot | `parental-monitor-ai-sync.timer` hourly (+10m jitter, persistent) | Rule sync, then top-20 unknowns to OpenRouter; 15-min timeout for slow free pools |
| `parental-monitor-dns-revert.service` | oneshot | `parental-monitor-dns-revert.timer` every 5 min (`Persistent=true`) | 3h Safe-DNS failsafe: reverts router DNS to `192.168.1.1` once the dashboard-started deadline passes. The ONLY automation allowed to touch router DNS |
| `nginx` | service | always-on | Serves `frontend/dist`, proxies `/api` + `/api/ws` |

Router DNS is **manual-only**: the retired `router-dns-guard.service`,
`/etc/systemd/system-sleep/router-dns`, and
`/etc/NetworkManager/dispatcher.d/99-router-dns-switch` are never
installed anymore — `install.sh` disables and deletes any deployed copies
(they once caused a WiFi-connected-but-no-internet outage). The dashboard
header switch (`POST /api/router-dns/mode`) is the sole writer besides the
failsafe timer above.

## Emergency reset

`infrastructure/scripts/reset-to-normal.sh` returns the PC and router to
normal while keeping data (DB, `.env`, logs): router DNS → `192.168.1.1`,
all units/timers removed, hooks/dispatcher/dnsmasq drop-in/nginx site
removed, `resolved.conf` default restored. `--dry-run` previews, `--yes`
applies; `uninstall.sh` delegates to it.

## Deploy checklist (learned the hard way — see ROADMAP incident log)

1. `npm run build` in `frontend/`, then copy `dist/index.html` +
   `dist/assets/*` explicitly — never `cp -r dist dist` (nests `dist/dist`).
2. Remove stale hashed bundles; verify the served hash matches the fresh
   build: `grep -o 'assets/index-[^"]*\.js' /opt/parental-safety/frontend/dist/index.html`.
3. Backend/collector go by file copy to `/opt/parental-safety`; restart
   the affected service (`systemctl restart parental-monitor-api`).
   Daemons load code at start — a file copy alone changes nothing running.
4. SQLite writes: stop the writer service first for multi-statement
   backfills; keep a timestamped copy in `/opt/parental-safety/backups/`.
5. After any scan-pipeline change, run both suites:
   `python3 -m pytest collector/tests/` (3 known IPv6 ARP failures) and
   the backend suite (1 known `test_devices` failure) from the repo root.
6. `nginx -t && systemctl restart nginx` when changing `listen`/proxy
   (reload doesn't always rebind).
