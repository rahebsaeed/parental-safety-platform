# Phase 1 Discovery: Network Reality, Architecture Decision, Implementation Plan

This document is the output of the discovery phase required before writing
any monitoring code. It exists so nobody — including future us — has to
re-derive these decisions later.

## The one fact that shapes everything

On WPA2/WPA3 Wi-Fi, **broadcast and multicast frames** (ARP requests/replies,
mDNS, DHCP discovery) are encrypted with a **Group Temporal Key (GTK)** that
every associated client holds. Any device on the network — including the
Ubuntu monitor — can see and originate them.

**Unicast frames** (a phone's actual DNS query, its HTTPS connection to the
router) are encrypted station-to-AP with a **Pairwise Transient Key (PTK)**
unique to that one client's session. No other client has that key. This is
true regardless of whether the observing device is on Wi-Fi or Ethernet, and
switching a NIC into monitor mode does not change it — monitor mode captures
more frames off the air, it does not decrypt someone else's pairwise key.

Consequences:

- **Device discovery** (who's on the network, by IP/MAC/hostname) only needs
  broadcast ARP — it works today, for any device, with zero router changes.
- **DNS/domain visibility** requires Ubuntu to be genuinely *on-path* for
  that traffic: either the DNS resolver devices are configured to use, or
  the network gateway itself. There is no passive-sniffing shortcut.

This is why Phase 1 (this document, and the code in `collector/device_discovery/`)
is scoped to discovery only, and why Phase 2's architecture depends on
router capabilities that have to be checked, not assumed.

## 1. Current network assumptions

No subnet, interface name, or gateway IP is hardcoded anywhere in this
codebase. `192.168.1.0/24` is common but not guaranteed.

Inwi commonly issues a ZTE ZXHN H267N or a Huawei EchoLife DG8245V-10 for
ADSL/fibre connections, both administered at `http://192.168.1.1` by
default — a reasonable starting guess, not a fact to code against. Inwi
4G/LTE routers are often on a different range entirely (frequently
`192.168.8.0/24` on Huawei 4G units). Confirm your actual subnet using
section 4 below before relying on anything.

Separately: your phones almost certainly present a private/randomized MAC
address on your home network by default, on both Android and iOS. This
isn't a malfunction or an evasion attempt — it's the OS default — and the
identity model in `collector/device_discovery/identity.py` is designed
around it rather than assuming factory MACs.

## 2. Required Ubuntu commands

```bash
ip addr show
ip route show
ip neigh show
ip -6 neigh show
resolvectl status
nmcli device status
nmcli device show <iface>        # security type, driver
nmcli connection show --active
cat /etc/resolv.conf
```

These must be run on the actual Ubuntu machine on your home network.
`scripts/network_reality_check.sh` runs all of them and saves the output to
a timestamped file for review.

## 3. Required packages

| Package | Purpose | Needed |
|---|---|---|
| `python3`, `python3-venv`, `python3-pip` | Everything | Now (standard on Ubuntu 24.04 desktop) |
| `scapy` (pip) | Active ARP scan | Now |
| `arp-scan`, `net-tools` | Optional manual cross-check | Now, optional |
| `avahi-utils` | mDNS hostname fallback (`avahi-resolve`), used automatically when installed | Now, optional — see "Figuring out which device is which" in `collector/README.md` |
| `tcpdump` | Visibility verification, Phase 2 debugging | Soon |
| `dnsmasq` or `unbound` | Local logging DNS resolver | Phase 2 |
| `nmap` | Optional cross-check, later OS fingerprinting | Optional |

## 4. Network topology detection procedure

1. Run the commands in section 2.
2. `ip route show` → the `default via <gw> dev <iface>` line gives the
   gateway and active interface.
3. `ip addr show <iface>` → the `inet a.b.c.d/N` line gives the subnet.
4. `resolvectl status` / `/etc/resolv.conf` → what DNS Ubuntu itself
   currently uses (usually the router, via systemd-resolved's stub
   listener at 127.0.0.53).
5. Log into `http://<gateway-ip>` and check the items in section 6.
6. If `ip addr show <iface>` shows a global `inet6` address, IPv6 is active
   — see the IPv6 note below.

`collector/device_discovery/network_info.py` performs steps 2-3
programmatically at runtime; nothing is hardcoded.

## 5. Architecture options (A/B/C/D)

| Architecture | Requires | Gives you | Status |
|---|---|---|---|
| A — Ubuntu runs the DNS service | Nothing from the router by itself | Full DNS visibility, but only for devices actually pointed at it | Phase 2, paired with B |
| B — Router hands out Ubuntu as DNS | Router exposes a custom DHCP-DNS option | Combined with A: the target architecture | Depends on router — see section 6 |
| C — Ubuntu becomes the gateway | Replacing the router's DHCP/routing role entirely | Sees everything, v4 and v6 | Deferred; only if B is unavailable, and only with explicit review before applying |
| D — Passive sniffing | N/A for unicast on encrypted Wi-Fi | Broadcast only: ARP, mDNS, DHCP discovery | **What Phase 1 uses**, for discovery only |

**Explicitly rejected: ARP spoofing** as a way to force other clients'
traffic through Ubuntu without becoming the real gateway. It works on some
networks, but it is a MITM technique: it degrades network reliability, gets
flagged by security software running on the very devices being observed,
and it is inconsistent with the "no exploitation of devices" principle this
platform is built on. If neither B nor C is achievable on this network, the
correct outcome is documented reduced visibility, not a spoofing workaround.

## 6. Router information required

Check on the router's admin panel (do not share credentials with any AI
assistant, including this one — report back yes/no findings instead):

- Custom DNS field under DHCP/LAN settings (determines whether B is available)
- Client/AP isolation status — if enabled, even Phase 1's ARP discovery
  won't see other Wi-Fi clients, since isolation blocks inter-client frames
  at the AP
- Whether IPv6 is enabled and what prefix is delegated
- Whether any connection/traffic log is exposed
- Exact model and firmware version (device label or admin status page)

Inwi's commonly-issued ZTE ZXHN H267N ships with a documented default
admin/password pattern, but check the physical label on your unit first, as
Inwi or a previous owner may have changed it.

## 7. Security considerations for Phase 1

- The active ARP scan needs raw-socket privileges — run via `sudo` for now.
  When this becomes a systemd service (Phase 11), it should drop to
  `CAP_NET_RAW`+`CAP_NET_ADMIN` on a dedicated interpreter rather than
  running fully as root indefinitely.
- Because `sudo` creates the SQLite file as root, the CLI checks for
  `SUDO_UID`/`SUDO_GID` (set by `sudo` itself) and hands the database file
  and its directory back to the invoking user after opening it — otherwise
  a `sudo scan` followed by a plain, non-sudo `scan` (passive-only mode,
  an explicitly supported way to run this tool) fails with
  `attempt to write a readonly database`. This was caught by testing
  against a real sudo invocation, not just unit tests with mocked
  permissions — see `collector/tests/test_cli_ownership.py`. If the
  database was ever created before this fix existed, or by running as
  root directly rather than through `sudo` (no `SUDO_UID` to hand
  ownership back to), fix it once with `sudo chown -R $USER:$USER data/`.
- All Phase 1 data lives in one local SQLite file. No telemetry, no
  outbound network calls beyond the LAN itself, nothing leaves the machine.
- Only network metadata is stored: IP, MAC, resolved hostname, vendor
  guess (if available), timestamps. No payload data, ever.
- SQL access is parameterized throughout `storage.py`, even though Phase 1
  has no network-facing input surface yet — that arrives in Phase 3, and
  the discipline should start now, not be retrofitted later.

## 8. Recommended technology stack

**Phase 1 (now):** Python 3.12, standard library + `scapy`, SQLite via the
stdlib `sqlite3` module, `pytest`. No FastAPI, Pydantic, SQLAlchemy, or
Postgres yet — there is no API or persistent multi-writer need to justify
them, and adding them now would be scope creep ahead of Phase 3/4.

**Later phases**, per the original spec: FastAPI + Pydantic + SQLAlchemy +
Alembic, PostgreSQL, React + TypeScript, WebSocket/SSE for real-time
updates.

Phase 1's SQLite schema (`devices`, `device_addresses`,
`device_status_events`) is deliberately shaped to map onto the normalized
tables in the original Section 16 schema, so Phase 4 can extend or migrate
it instead of starting over.

## 9. Phase 1 implementation

```text
collector/device_discovery/
├── network_info.py       Parses ip route / ip addr — interface, subnet, gateway
├── arp_scan.py            Active scapy ARP sweep + passive `ip neigh` fallback (v4 + v6)
├── hostname_resolver.py   Reverse DNS, falling back to mDNS (avahi-resolve) if installed
├── mac_vendor.py          Locally-administered (private/randomized) MAC detection;
│                          vendor-name lookup is a documented extension point
├── identity.py            Confidence-scored matching (HIGH / MEDIUM / LOW)
├── storage.py              SQLite persistence + lightweight schema migration
├── discovery_service.py    Orchestrates one scan cycle
├── logging_utils.py        Structured logging setup
└── cli.py                  scan / list / rename / classify / history
```

### Schema evolution before Alembic exists

Phase 1's SQLite schema will change more than once before Phase 4 replaces
it with real Alembic migrations against Postgres. `CREATE TABLE IF NOT
EXISTS` is a no-op against a database that already exists with an older
shape, so `storage.init_db()` also runs a small, explicit
`_ensure_schema_migrations()` step that checks for columns added after a
database may already have been created, and adds them in place via
`ALTER TABLE` — never by dropping and recreating. This was added after a
real user's already-populated database (named and classified devices)
would otherwise have silently never gained a new column. Every future
Phase 1 schema change needs the same treatment: additive, in-place,
data-preserving, until Phase 4's real migration system takes over.

### Why no hand-written MAC vendor table

A curated OUI-prefix-to-vendor table would need to be typed from memory,
and there's no way to guarantee every hex prefix is remembered correctly.
Shipping a wrong vendor guess in a monitoring tool is worse than not
guessing. The real registry is public domain and freely redistributable,
published by the IEEE at `https://standards-oui.ieee.org/oui/oui.txt`.
`mac_vendor.py` includes a loader for that exact format; fetching it is a
one-line `curl`, documented in `collector/README.md`, left to the user
rather than bundled with unverifiable content.

### MAC randomization and what it means for identity confidence

Checked at discovery time, not assumed:

- **Android** (10+) defaults to a randomized MAC that is **persistent per
  network** — it stays the same for a given SSID across reconnects, and
  only changes on a factory reset, or (per Android's own documentation)
  after roughly six weeks without joining that network. Non-persistent
  (per-connection) randomization exists as an opt-in setting on Android 12+
  but is not the default.
- **iOS** (18+) defaults to a **"Fixed" private address** — stable per
  network — for any WPA2/WPA3-secured network, which a home network
  normally is. "Rotating" (a new address roughly every two weeks) is the
  default only for open or weakly-secured networks.

Net effect: on a properly secured home network, both platforms keep a
*stable* (if not factory-original) MAC per network by default. That's why
`identity.py` treats a **consistently observed** MAC — private or not — as
building toward HIGH confidence, rather than permanently capping
randomized addresses at LOW. A brand-new, never-before-seen private MAC
starts at MEDIUM until that consistency is established.

## 10. Acceptance criteria for Phase 1

- `sudo python -m collector.device_discovery.cli scan` lists every device
  reachable via ARP on the local subnet: IP, MAC (if resolved), hostname
  (if resolvable), confidence-scored device ID.
- Running it twice reuses the same `device_id` for a device with a stable
  MAC, and marks devices absent from the second scan `offline`.
- Without `sudo`, it degrades to passive-only discovery with a clear
  warning instead of crashing.
- `rename` / `classify` / `history` / `list` work against the persisted
  SQLite store.
- `pytest` passes without root privileges or a real network.
- Structured log lines are emitted for each major step
  (`scan_started`, `device_detected`, `device_offline`, `scan_completed`,
  `scan_permission_denied`).
- No data leaves the machine; no payload data is ever stored.

## IPv6 scope for Phase 1

`ip -6 neigh show` is read passively (same as IPv4), so IPv6 neighbors
already in the OS's cache are surfaced. Active IPv6 discovery is **not**
implemented in Phase 1: IPv6 has no broadcast (it relies on multicast NDP),
most devices hold multiple addresses per interface (stable + temporary
"privacy extension" addresses that themselves rotate independently of Wi-Fi
MAC randomization), and getting this right needs more design than Phase 1's
scope allows. This is a documented gap, not a silent one — see
`docs/networking/visibility-and-limitations.md`.
