# Network Reality Check

Run this before trusting any assumption in this codebase about your
subnet, gateway, or interface — including the ones written in
`docs/architecture/phase-1-discovery.md`, which are informed guesses, not
facts about your specific network.

## Run it

```bash
bash scripts/network_reality_check.sh
```

This writes a timestamped report to `./reality-check-<timestamp>.txt` and
also prints it to the terminal. It only reads local state — it does not
touch the router and does not send any traffic beyond what the commands
themselves generate (mostly nothing; `ip`/`resolvectl`/`nmcli` are
read-only queries against the kernel and NetworkManager).

## How to read the output

| Look for | In the output of | Tells you |
|---|---|---|
| `default via X.X.X.X dev <iface>` | `ip route show` | Gateway IP and active interface |
| `inet A.B.C.D/N` under that interface | `ip addr show` | Your IP and subnet (the `/N` is the prefix length — `/24` means a `.0/24` network) |
| `link/ether XX:XX:XX:XX:XX:XX` | `ip addr show` | Ubuntu's own MAC on that interface |
| A list of `X.X.X.X dev <iface> lladdr ...` lines | `ip neigh show` | Devices already in the OS's ARP cache — a partial list, not the full LAN |
| DNS Servers line | `resolvectl status` | What Ubuntu itself currently resolves through — usually the router |
| `WPA2` or `WPA3` under security | `nmcli device show <iface>` | Confirms which Wi-Fi security is in use (relevant to the MAC-randomization notes in the discovery doc) |

## What this script deliberately does not do

It does not log into the router, does not change any configuration, and
does not perform an active ARP scan (that's `collector/device_discovery`,
which is a separate, explicit action requiring `sudo`). This script is
read-only reconnaissance of the Ubuntu machine itself.

## After running it

Cross-check the subnet/gateway you found against
`docs/architecture/phase-1-discovery.md` section 1. If your gateway isn't
`192.168.1.1`, that's fine — it just means you're not on the common
Inwi ADSL/fibre default, and `DISCOVERY_SUBNET`/`DISCOVERY_INTERFACE` in
`.env` may need to be set explicitly if auto-detection picks the wrong
interface (e.g. on a machine with both Wi-Fi and Ethernet active).
