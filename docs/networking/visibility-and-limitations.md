# What This Platform Can and Cannot See

This document is referenced throughout the project. Every dashboard,
alert, and analytics view eventually built on top of this platform must
stay inside these boundaries, and must label its output accordingly rather
than implying more certainty than the data supports.

## Directly observable (depending on architecture and configuration)

| Data | Available in | Notes |
|---|---|---|
| MAC addresses | Phase 1 | Often private/randomized — see identity model |
| Local IP addresses | Phase 1 | Changes with DHCP; not a stable identifier alone |
| Hostnames | Phase 1 | Best-effort only; many devices don't advertise one |
| Online/offline status | Phase 1 | Inferred from ARP responsiveness |
| DNS queries + responses | Phase 2, **if** Ubuntu is the resolver in use |
| Connection metadata (which device talked to which IP, when) | Phase 2/3, if on-path | Not packet contents |
| Traffic volume | Phase 2/3, if on-path | Bytes/packets, not content |
| Timestamps | All phases |

## Explicitly NOT available, and this platform will never claim otherwise

- HTTPS page contents
- Passwords
- Private messages, call contents
- Browser cookies or browser history databases
- Search queries made inside encrypted HTTPS (only the domain, if DNS is visible)
- The exact video/content watched — only the requested domain/service
- Encrypted application contents (Signal, WhatsApp, banking apps, etc.)

If a future feature would require any of the above, the answer is "we don't
build that feature," not "we find a way." See Section 18 of the original
spec and the project's threat model.

## Why passive sniffing doesn't get you unicast traffic

See `docs/architecture/phase-1-discovery.md` for the full explanation of
WPA2/WPA3 group-key (broadcast) vs. pairwise-key (unicast) encryption. The
short version: being another client on the same Wi-Fi network gets you
broadcast traffic (ARP, mDNS, DHCP) for free, and gets you nothing else.

## DNS encryption

Modern devices increasingly default to encrypted DNS that bypasses
whatever DNS visibility this platform achieves in Phase 2:

- **DNS-over-HTTPS (DoH)** — built into Chrome, Firefox, and increasingly
  the OS resolver itself
- **DNS-over-TLS (DoT)** — Android's "Private DNS" setting
- **iOS encrypted DNS profiles**

None of these are visible to a conventional DNS-log-based collector. When
they're in use for a given device, the platform must report:

```text
DNS visibility: PARTIAL
```

rather than silently showing incomplete data as if it were complete. This
status should be computed and surfaced per-device once Phase 2 exists —
e.g. by noticing a device's DNS query volume drop to near-zero while it
remains active on the network (ARP-visible, traffic-visible if on-path),
which is itself the signal that its DNS has moved somewhere the collector
can't see.

## Client / AP isolation

If enabled on the router, isolation prevents clients from exchanging
frames with each other directly — including the broadcast ARP that Phase 1
depends on. If Phase 1's discovery finds only the router and no other
devices, this is the first thing to check (see
`docs/architecture/phase-1-discovery.md`, section 6).

## IPv6

IPv6 has no broadcast (NDP uses multicast instead), and devices typically
hold multiple addresses per interface — a stable one and one or more
temporary "privacy extension" addresses that rotate independently of Wi-Fi
MAC randomization. Phase 1 reads the passive IPv6 neighbor table
(`ip -6 neigh show`) but does not perform active IPv6 discovery. If IPv6 is
active on your network (check via `ip addr show <iface>`), treat Phase 1's
device inventory as IPv4-complete and IPv6-partial until a later phase
addresses this properly.

## MAC randomization

Both Android (10+, persistent-per-network by default) and iOS (18+,
"Fixed" by default on WPA2/WPA3-secured networks) keep a private MAC
address stable per home network under normal circumstances. This platform
never claims a device's identity with full certainty — see the
HIGH/MEDIUM/LOW confidence model in `collector/device_discovery/identity.py`
and `docs/architecture/phase-1-discovery.md`.

## The standing rule

Every number, chart, or alert this platform ever produces must be
traceable to one of the rows in the first table above. "Network-derived
indicator," not "proof." This applies to future analytics (Section 11 of
the spec: request activity is not the same as time spent) and to future
application inference (Section 12: DNS traffic to a domain is not proof an
app was actively open) equally.
