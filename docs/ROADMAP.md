# Project Roadmap — All Phases

This is the single reference for where the project stands and what's next.
It supersedes the generic phase list from the original spec wherever
reality has since been confirmed — this document reflects what's actually
been tested on the real network, not what was originally assumed.

## Status legend

✅ Done and validated &nbsp;·&nbsp; 🔄 Ready to start (unblocked) &nbsp;·&nbsp;
⏳ Not started &nbsp;·&nbsp; 🔍 Needs investigation before it can start

## Confirmed facts about this network (stop guessing, these are known)

| Fact | Value | Confirmed by |
|---|---|---|
| Router | `DSL-G2452GE` (not the ZTE/Huawei models originally guessed) | Router admin panel + MAC vendor lookup on the gateway's own address |
| LAN subnet | `192.168.1.0/24` | `network_reality_check.sh`, multiple runs |
| Gateway | `192.168.1.1` | Same |
| Ubuntu's interface | `wlp0s20f3`, MAC `04:EA:56:FF:79:68` | Same |
| Ubuntu's LAN IP | `192.168.1.20`, now a **DHCP reservation** (no longer floating) | Router's Reserve IP feature, applied |
| Wi-Fi security | WPA2/WPA3 (`ADSL_inwi_5G_17B2`) | `nmcli device show` |
| IPv6 | Link-local only, no global prefix delegated | Both `ip addr show` (Phase 1) and the router's own IPv6 page independently agree |
| DHCP-handed DNS | **Configurable** — router has separate DNS/DNS2 fields under Settings → Network | Confirmed directly, the hard way (see incident log) |
| Client isolation | Not yet confirmed — still needs a direct check | — |

## Phase 1 — Network Discovery ✅ DONE

Discovers LAN devices via active ARP scan (root) with passive `ip neigh`
fallback (no root), resolves hostnames via reverse DNS then mDNS,
identifies devices with a HIGH/MEDIUM/LOW confidence model built around
real Android/iOS MAC-randomization behavior, and persists everything to
local SQLite with online/offline and IP-history tracking.

Validated in production across three real sessions, not just unit tests.
Real bugs found and fixed along the way, each confirmed with a live
reproduction before shipping the fix:

- `sudo`-created database was unwritable by later non-sudo runs (ownership fix + regression tests)
- Reality-check script only worked from one specific directory (made self-locating)
- MAC vendor lookups were computed but never displayed anywhere (added the column + fixed history output)
- The vendor-column fix needed a database already containing named, real devices to survive — added in-place schema migration rather than requiring a wipe

Full detail: `docs/architecture/phase-1-discovery.md`,
`docs/networking/visibility-and-limitations.md`.

## Phase 2 — DNS Observation 🔄 READY TO START

**Architecture: confirmed as B** — the router exposes DHCP-wide DNS
override fields, so devices can eventually be pointed at Ubuntu without
making Ubuntu the network gateway (Architecture C, the more invasive
option, is no longer needed).

### ⚠️ Incident log — read before touching router DNS settings again

While confirming this architecture, DNS/DNS2 were set to Ubuntu's LAN IP
before anything was actually listening on port 53 there. Every device on
the network immediately lost DNS resolution — not a Phase 1 bug, purely a
router DHCP setting with no resolver behind it yet. The firmware also
rejected blank DNS fields (its own "(optional)" label notwithstanding),
so recovery took two steps: temporarily setting real public DNS
(`8.8.8.8`/`8.8.4.4`) to restore service immediately, then a full router
reset to get back to the original default (the router's own IP,
`192.168.1.1`, acting as a relay).

Rules going forward, now backed by a real incident instead of a
hypothetical one:
1. **Never** point router-wide DHCP DNS at a service that isn't running
   and already tested.
2. Ubuntu's LAN IP must be a DHCP reservation before it's ever used as a
   DNS target — done (`04:EA:56:FF:79:68` → `192.168.1.20`), so it can no
   longer silently drift on reboot or lease renewal.
3. Test on **one device** first, via that device's own manual DNS
   override in its Wi-Fi settings — never router-wide — before touching
   DHCP-wide settings at all.
4. Write down the router's working DNS values before changing them.
   "Put it back" needs to be a fast, confident action during an outage,
   not a guess under pressure.
5. A 1-day DHCP lease time means devices don't necessarily pick up a
   DHCP-setting change until they reconnect or the router is rebooted —
   factor that into any test plan; don't assume a change is "not working"
   when it just hasn't propagated yet.

### Build plan

1. A local logging DNS resolver on Ubuntu (candidate: `dnsmasq` in
   forwarding+logging mode, or a small custom Python resolver using
   `dnslib` — decide based on how much control is needed over the exact
   log schema vs. how much is gained from a battle-tested existing tool).
   Records: `timestamp, source_ip, domain, query_type, response_status,
   resolved_addresses` (Section 7 of the original spec), joined against
   Phase 1's device table by source IP.
2. Runs on `192.168.1.20:53` (now permanent via the reservation),
   forwarding everything upstream to real DNS (the ISP's, or a public
   resolver) so it never becomes a single point of failure for browsing.
3. **Test order, strictly in this sequence:**
   - From Ubuntu itself (`dig @192.168.1.20 example.com`)
   - From exactly one other device, with **that device's own** Wi-Fi
     DNS setting manually pointed at `192.168.1.20` — not the router
   - Only after both work reliably: router-wide DHCP DNS override,
     with the pre-change values written down first
4. Explicit, permanent scope boundary (Section 31 of the original spec):
   devices using DNS-over-HTTPS/TLS or a "Private DNS" setting will not
   show up here at all. Phase 2 must detect and report this per-device as
   `DNS visibility: PARTIAL` rather than silently showing incomplete data
   as if it were complete.

## Phase 2 — DNS Observation ✅ Complete

Implemented and verified with real traffic:
- Local logging DNS forwarder (`dnsmasq`) on `192.168.1.20:53` with upstream forwarders (`8.8.8.8`, `8.8.4.4`).
- Real-time log ingester (`parental-monitor-dns start`) reading `/var/log/parental-safety/dnsmasq.log` and populating `dns_queries`.
- Joins source IP against Phase 1 `device_addresses` to attribute queries to `device_id`.
- Verified on single device (`dev_03` — 295+ queries attributed with 100% `FULL` visibility).
- Detection of bypassed/DoH queries as `PARTIAL` visibility.
- 133 automated unit and integration tests passing.

## Phase 3 — Backend API ✅ Complete

FastAPI + Pydantic v2 REST service exposing Phase 1 and 2 data:
- `GET /health` & `GET /api/health` — System status, database counters, daemon liveness.
- `GET /api/devices` — Discovered devices with current IP, MAC, query volume, and visibility status.
- `GET /api/devices/{device_id}` — Detailed history (IP/MAC observations, status events, recent domains).
- `PATCH /api/devices/{device_id}` — Rename device or update classification type.
- `GET /api/activity` — Paginated real-time DNS queries with filters (`device_id`, `domain`, `query_type`, `visibility`, `status`).
- `GET /api/domains/top` — Top domains queried across network or per device.
- `GET /api/dns/stats` — Query volume, visibility health, and private DNS bypass ratio.
- Interactive OpenAPI / Swagger UI at `/docs`.
- 18 automated unit and integration tests passing.

## Phase 4 — Database Architecture ✅ Complete

Formalized schema into SQLAlchemy 2.0 ORM models and Alembic migrations:
- SQLAlchemy 2.0 Declarative Models: `Device`, `DeviceAddress`, `DeviceStatusEvent`, `DnsQuery` with relationships, cascaded deletes, and explicit index declarations.
- Alembic database migration environment with baseline migration `0001_initial_schema.py`.
- Dual engine support: SQLite (WAL mode, busy timeouts, foreign keys) and PostgreSQL.
- Safe compatibility: live SQLite database stamped and preserved with zero data loss.
- 22 backend tests and 133 collector tests passing (155 total).

## Phase 5 — Domain Classification ✅ Complete

Rule-based classification engine and persistence layer categorizing network DNS activity:
- Standard 11-category classification model (`SOCIAL_MEDIA`, `STREAMING_VIDEO`, `GAMING`, `EDUCATION`, `PRODUCTIVITY`, `ADULT_CONTENT`, `ADS_TRACKING`, `TECH_INFRASTRUCTURE`, `NEWS_MEDIA`, `SHOPPING`, `UNCATEGORIZED`).
- Priority-ordered rule engine with LRU in-memory caching (`classify`, `classify_many`, `explain`).
- SQLAlchemy ORM model `DomainClassification` and Alembic migration `0002_domain_classification.py`.
- Operator override support (`is_override=1`) preventing automatic overwrite of custom definitions.
- REST API router:
  - `POST /api/classifications/classify` — On-the-fly real-time categorization.
  - `POST /api/classifications/sync` — Bulk classification of unclassified observed DNS domains.
  - `GET /api/classifications/domains` — Paginated domain catalog with category filtering.
  - `GET /api/classifications/domains/{domain}` — Single domain query with engine fallback.
  - `GET /api/classifications/summary` — Full category breakdown with UI metadata (colors, icons).
  - `PUT /api/classifications/domains/{domain}/override` — Manual category override.
- Verified on live network traffic: 132 unique domains synced and classified in `discovery.sqlite3`.
- 35 dedicated classification tests; full test suite of 190 tests passing (57 backend + 133 collector).

## Phase 6 — Safety Alerts ✅ Complete

Advisory safety detection subsystem with explainability and deduplication:
- Strict non-blocking philosophy (never drops packets or disrupts network browsing).
- Multi-vector detection:
  - Unsafe categories (Adult content -> `CRITICAL`, Online gambling -> `HIGH`).
  - Phishing & deceptive brand impersonation lures (PayPal, Apple ID, banking, crypto).
  - Encrypted DNS / DoH / DoT probes and `PARTIAL` visibility detection.
- Full explainability: every alert records `rule_matched`, category, and plain-language explanation.
- Intelligent deduplication: sliding cooldown window (default 1 hour) aggregates repeated events into an `occurrence_count` counter.
- SQLAlchemy ORM model `SafetyAlert` and Alembic migration `0003_safety_alerts.py`.
- REST API router (`GET /api/alerts`, `GET /api/alerts/summary`, `POST /api/alerts/scan`, `GET /api/alerts/{id}`, `PATCH /api/alerts/{id}`).
- Verified on live network queries: 852 DNS queries scanned, 23 alerts created, 8 aggregated.
- 25 dedicated alert tests; full platform test suite of 215 tests passing (82 backend + 133 collector).

## Phase 7 — Analytics ✅ Complete

Statistical aggregation and data export subsystem with strict ethical labeling:
- Scientific and ethical labeling: DNS telemetry is strictly labeled as "network-derived indicator of DNS request activity" and never misrepresented as "screen time" or "app usage" (Sections 11 & 34).
- Category distribution analytics: query counts, percentage share, distinct domain counts, UI colors/icons, per-device or network-wide.
- Active hours analytics: 24-hour histogram (00:00 to 23:59) revealing time-of-day request patterns.
- Daily timeline trend tracking query volume and active devices over time.
- Data export engine (Section 36):
  - Memory-efficient streaming CSV export (`GET /api/analytics/export/csv`).
  - Structured JSON export (`GET /api/analytics/export/json`).
  - Filtering by device, date range, and category.
- REST API router (`GET /api/analytics/overview`, `GET /api/analytics/categories`, `GET /api/analytics/active-hours`, `GET /api/analytics/timeline`, `GET /api/analytics/export/csv`, `GET /api/analytics/export/json`).
- Verified against live traffic: 950 queries analyzed across 157 unique domains.
- 15 dedicated analytics tests; full platform test suite of 230 tests passing (97 backend + 133 collector).

## Phase 8 — React Dashboard ✅ Complete

Modern, responsive single-page application built with React 19, TypeScript, and Vite with a custom Vanilla CSS design system:
- **Design System & Aesthetics**: Dark canvas (`#090d16`), glassmorphism cards, HSL category color tokens matching Phase 5 engine, Google Fonts (Outfit & Inter), live observer daemon status pulse.
- **Overview Dashboard**: Key metrics (queries, distinct domains, active devices, top category), visual category distribution progress bars, recent DNS queries feed.
- **Device Inventory**: Grid with hardware device classification icons (Smartphone, Laptop, Router, etc.), randomized MAC badges (LAA bit 1 detection), rename/classification modal, and address history inspection drawer.
- **Safety Alerts Console**: Severity filters (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`), triage action buttons (`ACTIVE`, `ACKNOWLEDGED`, `DISMISSED`, `RESOLVED`), explainability cards with exact rules and parent conversational guidance.
- **Activity Log Stream**: Searchable and filterable DNS query stream by domain substring, device ID, visibility mode (`FULL` vs. `PARTIAL`), and response status with pagination.
- **Analytics & Ethics**: Sections 11 & 34 ethical banner, 24-hour active hours histogram (00:00 to 23:00), 14-day volume timeline, and one-click streaming CSV and JSON exports.
- **Domain Rules & Sandbox**: Category directory, interactive real-time classifier testing sandbox, parent category override modal, and batch query sync.
- Production build verified (`npm run build`: 0 TypeScript errors, optimized production bundle in `dist/`).

## Phase 9 — Real-Time Updates ✅ Complete

WebSocket and Server-Sent Events (SSE) streaming subsystem connecting the local observer pipeline directly to the React dashboard:
- Dual-transport real-time architecture: Primary **WebSocket** (`/api/ws`) with automatic fallback to **Server-Sent Events** (`/api/events`).
- Typed JSON event envelopes for `dns_activity`, `safety_alert`, `device_status`, `connected`, and `pong`.
- In-memory async pub/sub `ConnectionManager` with heartbeat ping/pong protocol.
- `SqliteChangeWatcher` background worker tracking newly ingested queries, alerts, and device status events with sub-second latency.
- React frontend `useRealtime` hook with automatic exponential backoff reconnection.
- Live dynamic UI updates: prepending queries into the Activity stream and incrementing alert badges in real time without manual page reloads.
- 6 dedicated real-time automated tests; full platform test suite of 236 tests passing (103 backend + 133 collector).

## Phase 10 — Security Hardening ✅ Complete

Full threat model (Section 38) implemented against the real attack surface:
- **Parent authentication**: secure session tokens (32-byte `secrets.token_urlsafe`), HTTP-only cookie, configurable expiry (`SESSION_EXPIRE_HOURS`).
- **Rate limiting**: sliding-window IP-scoped limiter (120 req/min general; 5 req/min on `/auth/login`), `429 Retry-After` response.
- **CSRF origin validation**: mutating requests (`POST/PUT/PATCH/DELETE`) with an `Origin` or `Referer` header are rejected unless the origin is localhost, RFC1918, or in `CORS_ORIGINS`.
- **Security headers**: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `X-XSS-Protection`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy` injected globally by `SecurityMiddleware`.
- **Audit logging**: `audit_logs` table (Alembic migration `0004_audit_logs.py`) records every `AUTH_LOGIN_SUCCESS`, `AUTH_LOGIN_FAILED`, `AUTH_LOGOUT`, and `DEVICE_UPDATE` with timestamp, actor IP, and payload details.
- **Test suite**: 8 dedicated security tests; full platform suite of 111 tests passing (all backend).
- Full detail: `docs/architecture/phase-10-security.md` (inline with implementation).

## Phase 11 — Docker/Systemd Deployment ✅ Complete

All services are now managed by systemd and deployed via an idempotent installer:
- **`parental-monitor-collector.service`**: runs the DNS collector daemon with `AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN` — eliminates `sudo` entirely using a dedicated `parental-monitor` system user with a locked-down security profile (`NoNewPrivileges`, `ProtectSystem=strict`, `PrivateTmp`).
- **`parental-monitor-api.service`**: runs uvicorn on `127.0.0.1:8000` under the same restricted user; not exposed directly to the LAN.
- **nginx reverse proxy** (`infrastructure/nginx/parental-monitor.conf`): serves the pre-built React `dist/` on `192.168.1.20:80`, proxies `/api/*` and WebSocket upgrades (`/api/ws`) to the backend.
- **`install.sh`**: idempotent one-command installer — creates system user, syncs files, builds frontend, runs migrations, configures nginx, enables services.
- **`uninstall.sh`**: cleanly removes units and config; preserves data and `.env`.
- **Backup / Restore (Section 37)**: `backup.sh` uses `sqlite3 .backup` (safe while services run, WAL-mode aware), integrity-checked, with configurable retention rotation. `restore.sh` stops services, preserves the current DB as a pre-restore safety copy, swaps in the backup, and restarts.
- **Docker Compose** (`docker-compose.yml`): full stack for development portability — backend + nginx-frontend with a named data volume. Collector excluded (raw socket constraints).
- Full detail: `docs/architecture/phase-11-deployment.md`.

Validated live 2026-09-13: both units `active (running)`, migrations
0001→0004 applied to a fresh `/opt/parental-safety/collector/data/discovery.sqlite3`,
nginx bound to `192.168.1.20:80` serving React `dist/` + proxying `/api/health`
(healthy, ingester writing 1500+ queries). Fresh prod DB starts with
`devices_count=0` until the first discovery scan populates it — run one scan
post-install to attribute queries to devices.

## Phase 12 — Secure Remote Access ✅ Complete

Tailscale VPN access to the Phase 8 dashboard from outside the home network,
per Section 19 — the FastAPI server is never exposed directly to the internet.

- `tailscaled` on Ubuntu, Tailnet IP `100.99.54.78` (`tailscale up`, MagicDNS optional).
- nginx `listen 80` serves LAN (`http://192.168.1.20/`) + Tailnet
  (`http://100.99.54.78/`) from the same React `dist/` + `/api/` proxy;
  uvicorn stays on `127.0.0.1:8000`; no router port-forward exists.
- Phase 10 protections (parent password, rate limits, CSRF origin check,
  audit log) apply identically over Tailnet.
- Validated 2026-09-13: `tailnet-root:200`, `/api/health` healthy via Tailnet
  (`devices_count=6`, ingester writing), LAN access unchanged.

## Phase 12b — Device Matching & current_ip Fix ✅ Complete (2026-09-13)

Fixed two bugs that caused devices to show IPv6 link-local addresses
(`fe80::...`) instead of routable IPv4 (`192.168.1.x`) in the dashboard,
making DNS query attribution unreliable:

- **`backend/app/db/repository.py`**: `list_devices()` and `get_device()`
  `current_ip` subqueries now prefer IPv4 addresses via
  `INSTR(da.ip_address, '.') > 0` — IPv6 link-local entries never
  appear in the dashboard again.
- **`collector/device_discovery/arp_scan.py`**: `_parse_neighbor_lines()`
  now skips IPv6 link-local entries (`fe80::`) from the passive neighbor
  cache. Previously `read_passive_neighbors()` read both `ip neigh show`
  (IPv4) and `ip -6 neigh show` (IPv6), so a late IPv6 observation could
  overwrite an earlier IPv4 one as the device's "most recent" address.
- **Verified:** `current_ip` now shows IPv4 for all tracked devices
  (dev_01 gateway `192.168.1.1`, dev_02–dev_05 on `192.168.1.2–5`,
  dev_06 `None` because it has no IPv4). DNS queries properly attributed
  (`dns_visibility: FULL` for 4 devices with IPv4, `NONE` for devices
  with no routable address).

## Phase 13 — Password Change UI + On-Demand Scan ✅ Complete (2026-09-13)

Two operator requests: change the parent password from the dashboard
instead of editing `.env` over SSH, and make Refresh actually discover —
new devices, IP changes, and online/offline transitions.

- **`POST /auth/change-password`** (backend `routers/auth.py`): verifies
  current password, enforces min length 6, rewrites `PARENT_PASSWORD` in
  `/opt/parental-safety/.env`, updates in-memory `settings`, clears all
  sessions (old logins invalidated), writes `PASSWORD_CHANGED` audit row.
  API unit gained `ReadWritePaths=/opt/parental-safety/.env` so the
  `parental-monitor` user can persist the change under
  `ProtectSystem=strict`.
- **Settings tab** (frontend): new `SettingsPage.tsx` with current/new/
  confirm fields, success auto-reloads to the login page; `Sidebar.tsx`
  gains a Settings entry; `api.ts` gains `changePassword()`.
- **`POST /devices/scan`** (backend `routers/devices.py`): runs
  `collector.device_discovery.cli scan` via the collector venv with a
  120s timeout and returns success/output. Devices page gains a **Scan**
  button (`DevicesPage.tsx` + `App.tsx` `handleScan`); Header Refresh
  still reloads from DB, Scan runs discovery first.
- **Offline actually works now**: `cli._can_attempt_active_scan()` used
  to gate on `geteuid()==0`, so the API service (unprivileged user +
  `CAP_NET_RAW`) never attempted active ARP — every scan was
  passive-only and `mark_offline_except` never ran, so everything stayed
  `online` forever. Now detects `CAP_NET_RAW` via a raw-socket probe;
  verified `active_requested=True, active_scan_succeeded=True`,
  `devices_newly_offline=1` (dev_06). Passive scans additionally age out
  devices unseen for 30 min (`mark_stale_offline`), and the API reports
  an effective status (offline if `last_seen` older than 30 min) so the
  UI stays honest between scans.
- **API unit** (`parental-monitor-api.service`): added
  `AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN` (same as collector) so
  the scan subprocess can send ARP broadcasts.
- **Verified:** Scan finds new devices (dev_07 = S24-Ultra
  `4e:61:ba:9c:81:6a` at `192.168.1.5`), updates IPs, marks dev_06
  offline; `?status=online` → 6 devices, `?status=offline` → dev_06;
  password change → old login 401, new login 200, sessions revoked.

## Phase 14 — DNS Resolver Reliability ✅ Complete (2026-09-13)

When the router's DHCP DNS was pointed to `192.168.1.20`, other
devices lost internet. Root cause: dnsmasq was running as a manual
`nobody` process — not a systemd service — and could die silently
while `systemd-resolved`'s stub listener (`127.0.0.53`) competed
for port 53.

- **Created `dnsmasq.service`** (`infrastructure/systemd/dnsmasq.service`):
  proper systemd unit with `Type=simple`, `--no-daemon`, `User=nobody`,
  `AmbientCapabilities=CAP_NET_BIND_SERVICE`, `Restart=always`,
  `ReadWritePaths=/var/log/parental-safety /run`. `install.sh` now
  installs and enables it alongside the collector and API units.
- **Fixed `infrastructure/dnsmasq/setup.sh`**: `cmd_start()` now
  copies the systemd unit, `systemctl enable/restart dnsmasq`, and
  disables `systemd-resolved`'s stub listener (`DNSStubListener=no`).
  `cmd_stop()` uses `systemctl stop dnsmasq` when available.
- **`infrastructure/scripts/install.sh`**: added `dnsmasq` to
  `SERVICES` array; added Section 10 to disable `systemd-resolved`
  stub listener before systemd units are installed.
- **`/etc/dnsmasq.d/parental-safety-phase2.conf`**: removed
  `listen-address=192.168.1.20` + `bind-interfaces` (which caused
  conflicts when the old manual process held the port). Now binds
  `0.0.0.0:53` + `:::53` on all interfaces. Kept `no-resolv`,
  `server=8.8.8.8`, `server=8.8.4.4`, `log-queries`, `log-facility`.
- **Verified:** `dig @192.168.1.20 example.com` works;
  `resolvectl status wlp0s20f3` shows `DNS Servers: 192.168.1.20`;
  `systemctl is-active dnsmasq` is `active`; restarting the API
  service does not kill DNS.

## Phase 15 — AI-Assisted Classification ✅ Complete (2026-09-14)

Static rules can't name every new adult site, and an unlisted one slipped
through silently as UNCATEGORIZED. Free OpenRouter models now close the gap:

- **Verdict → rule mapping** (`openrouter_classifier.py`):
  `UNSAFE`/`GAMBLING` → `ADULT_CONTENT` (the only alert-firing category),
  `MESSAGING` → `SOCIAL_MEDIA`, etc.; `UNKNOWN` is never persisted so
  domains stay retryable. Model fallback chain
  (nemotron → gemma-4 → liquid) with per-model cooldowns on 429/404, 5s
  pacing between batch calls, and defensive parsing (colon/en-dash/bold
  formats, empty-200 payloads).
- **Persistence** (`classification_repo.ai_sync_uncategorized`): rule pass
  first (zero AI spend for known domains), then top UNCATEGORIZED domains
  by query volume, bounded per run; manual overrides (`is_override=1`)
  are never touched; commits before network I/O so long AI batches can't
  hold a SQLite write lock against the collector.
- **Closed-loop alerts**: `POST /alerts/scan` refreshes classifications
  *before* evaluating — a new adult domain is labeled then flagged in one
  scan. Verified: mocked UNSAFE verdict → stored `ADULT_CONTENT` →
  CRITICAL alert; live: `chatgpt.com` → `PRODUCTIVITY` persisted.
- **Visible UI** (Classifications page): sandbox Rules/AI toggle (AI panel
  shows static verdict alongside, Save-as-rule persists), per-row Ask AI
  buttons on UNCATEGORIZED rows, Sync reports AI counts; Settings holds
  the key (Test-validated), serving-model indicator, and last-verified
  timestamp. Key lives in the `settings` DB table, never `.env`/git.
- **30 major adult tube/studio/cam sites** added as static suffix rules
  (`beeg.com`, `chaturbate.com`, …) — deterministic, instant, immune to
  AI throttling; plus a `ts.net` infrastructure rule so Tailscale-rewritten
  domains can't false-positive as phishing.
- **Hourly `parental-monitor-ai-sync.timer`**: new domains are AI-resolved
  without anyone pressing Sync.

## Phase 16 — Safe-DNS Failover Control ✅ Complete (2026-09-14)

Protection only holds while the router advertises `192.168.1.20`, and the
old automation silently lost on suspend/shutdown (plus a 500 on the
Analytics security endpoint from a half-applied `/opt` edit).

- **Header control**: every dashboard page shows the router's *actual*
  reported DNS (green `rosa-PC` / amber `Router`) with a one-click switch;
  polled every 30s so automation can never leave the UI lying.
  New `GET/POST /api/router-dns/*` endpoints (5 tests) delegate switching
  to the canonical `router-dns.sh` — one source of truth.
- **Suspend**: new `/etc/systemd/system-sleep/router-dns` hook — failover
  *before* sleep (network still up, unlike shutdown ordering), restore on
  resume. Tested both directions live.
- **Shutdown/reboot**: replaced the racy `router-dns-on/off` pair with
  `router-dns-guard.service` — a persistent guard whose ExecStop runs
  *before* NetworkManager stops, so the fallback still has a network.
- **Logout**: verified no hook needed — the WiFi connection is
  system-wide (`connection.permissions` empty) and survives logout; any
  real disconnect is already caught by the NM dispatcher.
- **Analytics 500**: stored rules (static/AI/override) now take precedence
  over keyword heuristics in `/api/domains/security|dangerous|subjects`,
  with `ADULT_CONTENT` → Dangerous — the half-applied openrouter block
  that referenced an unimported name is gone.

## Phase 17 — Discovery Hardening ✅ Complete (2026-09-14)

New devices (e.g. `.15`/Ahmed-PC, S24-Ultra after a DHCP move) appeared
in DNS history as permanent Unassigned: scans missed them, attribution
only ran at ingest, and a same-subnet fallback sprayed their queries
onto unrelated devices (`.5` → dev_07 while dev_07 sat at `.6`).

- **Router DHCP leases as a scan source** (`router_clients.py`): login →
  `home_getclientList.asp` → parse/decode, merged with ARP results every
  cycle (deduped, best-effort, secrets never logged). Immediately found
  HONOR-X8a as dev_08.
- **DNS-driven placeholders** (`ingester.py`): first query from an
  unknown private IP creates a LOW-confidence device and attributes from
  sighting #1 — Unassigned-while-querying is now impossible.
- **IP-adoption** (`identity.py`): a scan observing (same IP + MAC)
  enriches the placeholder instead of duplicating it; claimed MACs still
  match their true owners first.
- **Asking = alive**: devices with DNS queries in the last 30 min are
  exempt from offline-marking, so quiet/static-IP hosts stop flapping.
- **Exact-match attribution only**: the subnet fallback is deleted
  (a wrong device is worse than an honest unknown); affected S24 history
  backfilled after a timestamped backup.
- **Hourly `parental-monitor-scan.timer`** keeps mappings fresh across
  DHCP moves; **timestamps fixed** (dnsmasq local time was stamped as
  UTC, +1h skew on every row).

## Incident Log

A running record of real production incidents, for the same reason
Phase 10's threat model should eventually reference real events, not just
hypothetical ones.

| Date | What happened | Root cause | Fix | Prevention added |
|---|---|---|---|---|
| 2026-09-12 | Household-wide internet outage | Router's DHCP-wide DNS/DNS2 fields were pointed at Ubuntu's IP before any resolver was running there | Reset DNS to public resolvers (`8.8.8.8`/`8.8.4.4`), then router reset to restore the original default | Ubuntu's IP is now a DHCP reservation; Phase 2's build plan mandates single-device testing before any router-wide DNS change |
| 2026-09-13 | Phase 11 installer aborted at venv + migrations; no units/`.env` | Stale `/opt` installer ran `pip install -e /opt/parental-safety` (no pyproject there); `backend/alembic.ini` used cwd-relative `script_location=alembic` | Pinned installs to `collector/` + `backend/`; changed ini to `%(here)s/alembic` + absolute `-c` path; moved `.env` creation before migrations with absolute prod DB paths; fixed collector unit `parental_monitor.dns.cli` → `collector.dns.cli` + explicit `DISCOVERY_DB_PATH`/`DATABASE_PATH` env | `install.sh` is now re-runnable idempotently; `backend/app/core/config.py` falls back to `/opt` (no `$HOME` hardcode); rsync excludes `backups/` + cleans stale `.cache`/`.rustup` |
| 2026-09-13 | nginx served Welcome page, `/api/*` 404 after install | `systemctl reload` didn't rebind listeners (`0.0.0.0:80` still held by old default); broken PPA also blocked `apt install nginx` via `&&` | Removed broken PPA, installed nginx separately, `systemctl restart nginx` → `192.168.1.20:80` serving React + proxy | Install docs: never chain `apt update && apt install` when a third-party repo can fail; prefer `restart` over `reload` when changing `listen` directives |
| 2026-09-13 | Dashboard showed IPv6 `fe80::` current_ip instead of IPv4 | Passive neighbor cache (`ip -6 neigh show`) picked up link-local IPv6 entries that overwrote IPv4 observations; `current_ip` subquery picked most-recent regardless of address family | Filter `fe80::` in `_parse_neighbor_lines`; prefer IPv4 via `INSTR(ip_address, '.') > 0` in repository queries | Dashboard now shows routable IPv4 for all tracked devices |
| 2026-09-13 | `cp -r dist /opt/.../dist` created nested `dist/dist`, UI served stale JS | `cp -r src dest` copies src *inside* dest when dest exists | Copy `dist/index.html` + `dist/assets/*` explicitly, remove stale hashed bundles | Deploy checklist: verify `/assets/index-*.js` hash matches fresh build |
| 2026-09-13 | All devices stuck `online`; Refresh never found new devices/IPs | API service gated active ARP on `geteuid()==0` so scans were always passive-only and `mark_offline_except` never ran; no Scan trigger existed | Added `POST /devices/scan` + Scan button; detect `CAP_NET_RAW` via raw-socket probe; 30-min stale-offline aging in passive scans + effective-status in API | Verified active scan succeeds from API service, dev_06 correctly offline |
| 2026-09-13 | DNS broke after pointing router at 192.168.1.20 | dnsmasq ran as a manual `nobody` process (no systemd service); `systemd-resolved` stub listener competed on 127.0.0.53; old manual process held port 53 in a user namespace preventing service start | Created `dnsmasq.service` with `Type=simple` + `--no-daemon`; disabled `systemd-resolved` stub listener; `setup.sh` now installs the systemd unit | `systemctl is-active dnsmasq` always active, `dig @192.168.1.20` resolves |
| 2026-09-14 | S24-Ultra's requests split across dev_07/NULL; new devices stuck Unassigned | Same-subnet fallback in `resolve_device_id_for_ip` attributed unknown IPs to the most-recently-seen device; scans (the only mapping source) missed DHCP-moved/static-IP hosts | Deleted the fallback (exact-match only); ingester creates IP-only placeholders on first sighting; scans enrich via IP-adoption; hourly scan timer; backfilled `.5` → dev_05 after backup | Unknown private IP can no longer stay Unassigned past its first query |
| 2026-09-14 | Every `occurred_at` 1h in the future | `log_parser` stamped dnsmasq's local-time log lines as UTC | Interpret naive stamps as local, convert to UTC (round-trip test included) | New rows match real UTC; old rows left as-is (documented skew window) |
| 2026-09-14 | `/api/domains/security` 500 on any UNKNOWN domain | Half-applied `/opt`-only edit constructed `DomainSecurity(...)` without importing it; repo copy didn't match prod | Removed the block; stored rules now take precedence over keywords in all three endpoints; repo↔`/opt` diff-checked | Deploy checklist: diff repo vs `/opt` for every touched backend file before restart |
| 2026-09-14 | `L.map`/`w.map`/`q.map is not a function` console errors | Misdiagnosed as minifier bug twice (renames, terser) — actually `GET /api/activity` returns `{items:[...]}` and callers mapped the envelope object | Unwrap `.items` in `api.getActivity` + `Array.isArray` guards | API doc now states paginated shape explicitly; verify with Network tab, not bundle archaeology |
