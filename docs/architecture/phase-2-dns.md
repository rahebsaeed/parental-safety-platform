# Phase 2 — DNS Observation Architecture

## Summary

Phase 2 adds a local logging DNS resolver on Ubuntu's LAN IP
(`192.168.1.20:53`). Every DNS query made by any device on the network is
forwarded upstream and logged. The logs are parsed by a Python ingester and
stored in the same SQLite database Phase 1 uses for device discovery,
enabling joined queries like "which device queried social-media.com at 23:00."

Architecture B was chosen after confirming it directly in the router admin
panel: the DSL-G2452GE exposes DHCP-wide DNS override fields, so Ubuntu can
become the network's DNS resolver without becoming the network gateway
(Architecture C, the more invasive option, is not needed).

## Component Overview

```
Network devices                Ubuntu (192.168.1.20)
──────────────                 ─────────────────────
Phone/tablet/laptop  ─DNS─►  dnsmasq :53
                                 │  logs to /var/log/parental-safety/dnsmasq.log
                                 │  forwards upstream to 8.8.8.8 / 8.8.4.4
                                 ▼
                              ingester (Python, polls every 5s)
                                 │  parses log lines
                                 │  joins source_ip → device_id (Phase 1 DB)
                                 ▼
                              discovery.sqlite3 (dns_queries table)
                                 │
                                 ▼
                              parental-monitor-dns tail / status
```

## Files

| File | Purpose |
|---|---|
| `infrastructure/dnsmasq/dnsmasq-phase2.conf` | dnsmasq config (DNS-only, logging, no DHCP) |
| `infrastructure/dnsmasq/setup.sh` | Start/stop/status/test script with safety gates |
| `collector/dns/log_parser.py` | Parses dnsmasq log lines → `DnsLogEntry` |
| `collector/dns/ingester.py` | Tails log file, writes to SQLite |
| `collector/dns/cli.py` | `parental-monitor-dns` CLI |
| `collector/device_discovery/storage.py` | Extended with `dns_queries` table + functions |

## DNS Visibility

Not every query from every device will appear here. The `dns_visibility`
field on each `dns_queries` row reports the quality of the data:

| Value | Meaning |
|---|---|
| `FULL` | Query seen + attributed to a known Phase 1 device |
| `PARTIAL` | Query seen, but the source IP is unknown to Phase 1 (device never scanned, or using DoH/DoT) |

When `parental-monitor-dns status` shows `⚠️ DoH/DoT bypass suspected` for a
device, that device is making DNS requests that bypass this resolver entirely.
This is reported, never silently ignored (per Section 31 of the original spec).

## 3-Stage Test Sequence

**This sequence is mandatory before touching router-wide DNS settings.**
The 2026-09-12 household-wide outage was caused by skipping stage 1 and
pointing the router directly at a non-running resolver.

### Stage 1 — Ubuntu self-test

```bash
# Start dnsmasq
sudo bash infrastructure/dnsmasq/setup.sh start

# Verify it resolves from Ubuntu itself
dig @192.168.1.20 example.com

# Check the ingester can see and parse queries
cd collector
source .venv/bin/activate
parental-monitor-dns start &
parental-monitor-dns tail      # should show the example.com query
```

Only proceed to Stage 2 once `dig` returns a real IP and `tail` shows the query.

### Stage 2 — Single device manual override

On **one** phone or laptop (not the router):
1. Wi-Fi settings → DNS → manually set to `192.168.1.20`
2. Browse a few websites
3. Run `parental-monitor-dns tail` — queries should appear
4. Run `parental-monitor-dns status` — the device's `device_id` should show up
   with `FULL` visibility (assuming Phase 1 has scanned it before)

Only proceed to Stage 3 once this works reliably.

### Stage 3 — Router-wide DHCP DNS override

> [!WARNING]
> **Write down the current DNS values before touching anything.**
> "Put it back" must be a fast, confident action during an outage, not a guess.

Current values to record:
- Router: http://192.168.1.1 → Settings → Network
- DNS field: `_____________` (write it before changing)
- DNS2 field: `_____________` (write it before changing)

Then set:
- DNS: `192.168.1.20`
- DNS2: `8.8.4.4` ← fallback so the network doesn't die if dnsmasq stops

To revert instantly:
- DNS: `192.168.1.1` (the router's own relay, original default)
- DNS2: (blank or `8.8.4.4`)

Note: with a 1-day DHCP lease, devices may not pick up the new DNS until they
reconnect or the router is rebooted. Don't assume a change isn't working —
wait or force a reconnect before diagnosing.

## Database Schema (dns_queries table)

```sql
CREATE TABLE dns_queries (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at        TEXT    NOT NULL,          -- ISO-8601 UTC
    source_ip          TEXT    NOT NULL,          -- who asked
    device_id          TEXT    REFERENCES devices(device_id),  -- NULL = unknown
    domain             TEXT    NOT NULL,
    query_type         TEXT    NOT NULL,          -- A, AAAA, CNAME, ...
    response_status    TEXT    NOT NULL DEFAULT 'NOERROR',
    resolved_addresses TEXT,                      -- comma-separated IPs, or NULL
    dns_visibility     TEXT    NOT NULL DEFAULT 'FULL'  -- FULL | PARTIAL
);
```

The `device_id` foreign key links directly into Phase 1's `devices` table,
enabling queries like:
```sql
SELECT d.friendly_name, q.domain, q.occurred_at
FROM dns_queries q
JOIN devices d ON d.device_id = q.device_id
WHERE q.occurred_at > datetime('now', '-1 day')
ORDER BY q.occurred_at DESC;
```

## Ingester Position Tracking

The ingester writes its current byte offset into `.dns_ingester_pos` (next
to the database file). On restart it resumes from that offset, so no queries
are duplicated and no history is lost. If the log file shrinks (dnsmasq
rotated it), the ingester detects this and resets to position 0.

## CLI Reference

```bash
# Start the ingester loop (blocks until Ctrl+C)
parental-monitor-dns start

# Show the 50 most recent DNS queries
parental-monitor-dns tail

# Show fewer rows
parental-monitor-dns tail --limit 20

# Per-device visibility summary
parental-monitor-dns status

# Use a non-default database or log file
parental-monitor-dns --db-path /path/to/db.sqlite3 tail
parental-monitor-dns start --log-path /path/to/dnsmasq.log
```

## Scope Limitations (Section 31)

Devices using DNS-over-HTTPS (DoH) or DNS-over-TLS (DoT) — or any "Private
DNS" setting — will not appear in Phase 2's data. This is a deliberate
architectural constraint, not a bug. Phase 2 detects and reports these as
`dns_visibility = PARTIAL` rather than silently presenting incomplete data as
if it were complete.

Known clients that may bypass this resolver:
- Android devices with "Private DNS" set to a provider like `dns.google`
- iOS devices with a DNS profile installed via MDM or the Settings app
- Browsers with DoH enabled (Chrome, Firefox — though this depends on policy)

Phase 5 (Domain Classification) and Phase 6 (Safety Alerts) will always
work with the `PARTIAL` label visible to the user.
