# Phase 11 — Deployment Guide

This document describes how to deploy the Parental Safety Platform as persistent, auto-starting services on your Ubuntu machine. It covers both the native systemd path (recommended for the home server) and the Docker Compose path (for portability/development).

---

## Architecture overview

```
Internet
   │
Router (192.168.1.1 / DSL-G2452GE)
   │  DNS: 192.168.1.20 (→ dnsmasq → 8.8.8.8)
   │
Ubuntu (192.168.1.20, DHCP reservation)
   │
   ├── dnsmasq (port 53) ─────────────── captures DNS queries
   │       │
   ├── parental-monitor-collector ───── reads dnsmasq log, writes SQLite
   │       │  (systemd, CAP_NET_RAW)
   ├── parental-monitor-api ──────────── FastAPI on 127.0.0.1:8000
   │
   └── nginx (port 80) ──────────────── serves React app + proxies /api/*
           │
    LAN devices → http://192.168.1.20/
```

---

## Path A — Systemd (production, recommended)

### Prerequisites

```bash
sudo apt install nginx sqlite3 rsync python3-venv
```

Node.js (for building the frontend — only needed during install):

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install nodejs
```

### Install

```bash
cd /path/to/parental-safety-platform
sudo infrastructure/scripts/install.sh
```

The script is **idempotent** — safe to re-run after updates.

What it does:
1. Creates `parental-monitor` system user (no login shell)
2. Copies project to `/opt/parental-safety/`
3. Creates Python venv, installs backend + collector packages
4. Runs `npm run build` for the React frontend
5. Runs Alembic database migrations
6. Generates a random `PARENT_PASSWORD` in `/opt/parental-safety/.env`
7. Installs and enables systemd service units
8. Configures nginx and reloads it

### First login

After install, find your generated password:

```bash
sudo grep PARENT_PASSWORD /opt/parental-safety/.env
```

Open `http://192.168.1.20/` in your browser and enter the password.

### Checking service status

```bash
systemctl status parental-monitor-collector
systemctl status parental-monitor-api

# Live logs
journalctl -fu parental-monitor-collector
journalctl -fu parental-monitor-api
```

### Updating

```bash
cd /path/to/parental-safety-platform
git pull
sudo infrastructure/scripts/install.sh
```

The install script re-syncs files, rebuilds the frontend, and restarts services.

### Uninstalling

```bash
sudo infrastructure/scripts/uninstall.sh
```

This stops services and removes config files. Your database and `.env` are **not** deleted.

---

## Capability hardening (no more sudo for ARP)

The collector uses `AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN` in its systemd unit. This grants only the specific capabilities needed for raw-socket ARP scanning to the `parental-monitor` process — without running as root.

The security profile is:
- `NoNewPrivileges=yes` — cannot escalate further
- `ProtectSystem=strict` — filesystem is read-only except `ReadWritePaths`
- `PrivateTmp=yes` — isolated `/tmp`
- Only `ReadWritePaths` can be written: `/opt/parental-safety/collector/data` and `/var/log/parental-safety`

---

## Backup & Restore (Section 37)

### Manual backup

```bash
/opt/parental-safety/infrastructure/scripts/backup.sh
# Creates: /opt/parental-safety/backups/discovery_YYYYMMDD_HHMMSS.sqlite3.bak
```

The backup uses SQLite's `.backup` command — **safe while services are running** (WAL mode handles concurrency). Each backup is integrity-checked before being saved.

### Automated backup with cron

```bash
sudo crontab -e
```

Add this line to back up daily at 03:00 and keep 30 days of history:

```cron
0 3 * * * /opt/parental-safety/infrastructure/scripts/backup.sh \
           /opt/parental-safety/backups \
           >> /var/log/parental-safety/backup.log 2>&1
```

### Restore from backup

```bash
sudo infrastructure/scripts/restore.sh \
    /opt/parental-safety/backups/discovery_20260913_030000.sqlite3.bak
```

The restore script:
1. Stops services
2. Saves the current DB as a pre-restore safety backup
3. Swaps in the chosen backup
4. Restarts services

---

## Path B — Docker Compose (development / portability)

> **Note**: The collector cannot run in Docker (raw socket ARP scanning). Docker Compose covers API + frontend only.

### Build and start

```bash
cp .env.example .env
# Edit .env: set PARENT_PASSWORD to something secure

docker compose up -d
```

Dashboard: `http://localhost/` (or `http://192.168.1.20/` if port 80 is free)

### Inspect

```bash
docker compose logs -f backend
docker compose logs -f frontend
docker compose ps
```

### Stop

```bash
docker compose down          # stop containers (keeps data volume)
docker compose down -v       # stop + delete data volume
```

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Dashboard shows no data | `journalctl -u parental-monitor-collector` — is dnsmasq logging? |
| WebSocket disconnects through nginx | Check `proxy_read_timeout` in nginx config (should be `3600s`) |
| `502 Bad Gateway` | `systemctl status parental-monitor-api` — uvicorn running? |
| ARP scan not working | `journalctl -u parental-monitor-collector \| grep -i cap` — AmbientCapabilities set? |
| Can't reach dashboard | `nginx -t` — config OK? Port 80 not used by another service? |
| Backup fails | `sqlite3 --version` — sqlite3 CLI installed? |

---

## File layout after install

```
/opt/parental-safety/
├── .env                        ← secrets (never committed)
├── backend/                    ← FastAPI source
├── collector/
│   ├── .venv/                  ← Python virtual environment
│   └── data/
│       └── discovery.sqlite3   ← live database
├── frontend/
│   └── dist/                   ← built React app (served by nginx)
├── infrastructure/
│   ├── nginx/parental-monitor.conf
│   ├── scripts/
│   │   ├── backup.sh
│   │   └── restore.sh
│   └── systemd/
│       ├── parental-monitor-collector.service
│       └── parental-monitor-api.service
└── backups/                    ← timestamped SQLite backups
```
