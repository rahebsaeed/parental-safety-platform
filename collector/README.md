# Collector — Phase 1: Device Discovery

Standalone Python package. No backend, database server, or web framework
required — it writes to its own local SQLite file. This independence is
deliberate: it's meant to run as its own systemd service later
(`parental-monitor-collector.service`, Phase 11) regardless of what the
backend/frontend end up looking like.

## Setup

```bash
cd collector
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running the active scan

The active ARP scan (`scapy`) needs raw-socket privileges:

```bash
sudo .venv/bin/python -m collector.device_discovery.cli scan
```

Using `sudo .venv/bin/python` (not plain `sudo python`) matters — it keeps
the venv's installed packages available under sudo instead of falling back
to the system interpreter.

Without `sudo`, the same command still runs, but falls back to
passive-only discovery (reading the OS's existing ARP cache via
`ip neigh show` instead of actively probing the subnet) and prints a
warning explaining the reduced visibility. It will not silently pretend to
have scanned when it didn't.

Running `scan` under `sudo` and then later without it (or vice versa) is
expected and supported: the CLI detects when it's running as root via
`sudo` (checking `SUDO_UID`/`SUDO_GID`) and hands the database file and
its directory back to the invoking user afterward, so a root-owned
database from one run doesn't lock out a normal-user run afterward. If you
ever hit `sqlite3.OperationalError: attempt to write a readonly database`
anyway (e.g. because the database was created before this fix existed, or
by running as root directly rather than through `sudo`), fix it once —
run this from wherever your `data/` directory actually is (inside
`collector/`, if you're using the default `DISCOVERY_DB_PATH`):

```bash
sudo chown -R $USER:$USER data/
```

## CLI commands

```bash
python -m collector.device_discovery.cli scan                     # scan + display
python -m collector.device_discovery.cli list                     # display without scanning
python -m collector.device_discovery.cli rename dev_01 "Samsung Phone"
python -m collector.device_discovery.cli classify dev_01 Android
python -m collector.device_discovery.cli history dev_01            # IP history for one device
```

Data is stored in `./data/discovery.sqlite3` by default (created
automatically). Override with the `DISCOVERY_DB_PATH` environment variable
or `--db-path`.

## Figuring out which device is which, before you rename anything

`history`, `list`, and `rename`/`classify` all work on any device_id at
any time — you don't need to identify every device before using the tool,
and you can rename them in any order, whenever you're confident. In rough
order of effort:

1. **Check the router's own client list.** Log into `http://<gateway-ip>`
   and look for "connected devices" or "DHCP clients." Routers often
   learn a real device name (e.g. "Sara-iPhone") directly from the DHCP
   request itself — something Ubuntu has no way to see from outside —
   even when nothing else here resolves a hostname.
2. **Check the device's own Wi-Fi settings.** Android: Settings → About
   phone → Status → Wi-Fi MAC address. iOS: Settings → General → About →
   Wi-Fi Address. Windows: `ipconfig /all`. This is the single most
   reliable method: since both Android and iOS keep a private MAC stable
   per network by default (see `docs/architecture/phase-1-discovery.md`),
   what the device reports for *this* Wi-Fi network should match what
   `list` shows exactly.
3. **Disconnect one device and rescan.** Turn off Wi-Fi on a device you
   can identify by elimination, run `sudo .venv/bin/python -m
   collector.device_discovery.cli scan` again, and see which device_id
   goes offline. Completely reliable, no guessing, costs one scan.
4. **Let the tool try automatically.** `scan` now attempts mDNS/Bonjour
   resolution (`avahi-resolve`) as a fallback whenever reverse DNS comes
   up empty — install it with `sudo apt install avahi-utils` if you
   haven't already. This resolves Apple devices especially reliably, and
   many Android phones and smart-home devices too, but it's still
   best-effort: silence from a device means it isn't advertising itself
   this way, not that anything is broken. Check `list` after installing
   avahi-utils and rescanning — some hostnames may already have appeared.
5. **MAC vendor as a hint, not proof.** A non-randomized MAC's OUI prefix
   identifies the *manufacturer* (see below) — useful for "this is
   Samsung-made" but not which specific device you own if you have more
   than one from that vendor.

## Running tests

```bash
pytest
```

All tests run against fixture text (sample `ip neigh`/`ip route` output)
and temporary SQLite files. None of them require root privileges or a real
network — that's intentional, so CI and this exact sandbox can both run
them, and so the parsing/matching logic is verified independently of
whether a live scan is even possible in a given environment.

## Optional: real MAC vendor lookups

`mac_vendor.py` always detects locally-administered (private/randomized)
MACs correctly — that's a bit-flag check, not a lookup. For actual
manufacturer names on non-randomized MACs, download the real IEEE registry
yourself (public domain, freely redistributable):

```bash
curl -o oui.txt https://standards-oui.ieee.org/oui/oui.txt
```

Then point the CLI at it:

```bash
python -m collector.device_discovery.cli scan --oui-file oui.txt
```

Without `--oui-file`, vendor is reported as `"Unknown (no OUI database
loaded)"` for non-randomized MACs and `"Private/randomized address"` for
randomized ones — both true statements, rather than a guess.

## Known limitations (Phase 1)

- IPv4 active discovery only; IPv6 is passive-observation-only (see
  `docs/networking/visibility-and-limitations.md`)
- Hostname resolution tries reverse DNS, then mDNS (`avahi-resolve`) as a
  fallback. Between the two, a meaningful fraction of devices will still
  resolve to nothing — that's expected on most home networks, not a bug.
  See "Figuring out which device is which" above for what actually works
  when neither does.
- Identity matching is best-effort (see `identity.py` docstring) — it will
  occasionally create a new device record for a device that changed both
  its MAC and hostname at once, and a parent may need to merge/rename
  manually. There is no fully reliable way to solve this from network data
  alone.
