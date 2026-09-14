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
| `router-dns-guard.service` | oneshot + RemainAfterExit | boot (ExecStart) / shutdown (ExecStop) | Router DNS → dnsmasq while PC is up, → router on the way down. ExecStop runs *before* NetworkManager stops, so the fallback still has network (the old `Before=shutdown.target` starter raced WiFi teardown and lost) |
| `nginx` | service | always-on | Serves `frontend/dist`, proxies `/api` + `/api/ws` |

Plus, outside systemd: `/etc/systemd/system-sleep/router-dns`
(failover before suspend, restore after resume) and
`/etc/NetworkManager/dispatcher.d/99-router-dns-switch` (WiFi up/down).
Logout needs no hook — the WiFi connection is system-wide
(`connection.permissions` empty) and survives it.

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
