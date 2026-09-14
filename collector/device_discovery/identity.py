"""Device identity matching with honest confidence scoring.

Handles: DHCP address changes, randomized/private MAC addresses, hostname
changes, devices temporarily disappearing, and multiple devices sharing
similar hostnames — by never claiming more certainty than the evidence
supports. See docs/architecture/phase-1-discovery.md ("MAC randomization
and what it means for identity confidence") for the research this is based
on.

This module is intentionally decoupled from storage.py: it takes plain
data in and returns a plain decision, so it can be unit-tested without a
database (collector/tests/test_identity.py) and so storage.py doesn't need
to know how matching decisions are made.

Known limitation, stated plainly rather than hidden: if a device changes
its MAC *and* its hostname in the same scan cycle (e.g. a phone with
non-persistent MAC randomization enabled, and no advertised hostname),
this module cannot distinguish that from a brand-new device. It will
create a new record. There is no way to solve this reliably from network
metadata alone — a parent may need to merge records manually via the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from collector.device_discovery.mac_vendor import (
    InvalidMacAddressError,
    is_locally_administered,
    normalize_mac,
)

_GENERIC_HOSTNAMES = {"android", "iphone", "localhost", "unknown", "device"}


class Confidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class KnownDevice:
    """Minimal view of a stored device needed to attempt a match.
    Deliberately not storage.DeviceRecord, to keep this module storage-agnostic.
    """

    device_id: str
    primary_mac: str | None
    last_hostname: str | None
    last_ip: str | None = None


@dataclass(frozen=True)
class Observation:
    ip: str
    mac: str | None
    hostname: str | None


@dataclass(frozen=True)
class MatchResult:
    device_id: str | None  # None means: create a new device
    confidence: Confidence
    reason: str
    mac_is_randomized: bool


def _is_specific_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    cleaned = hostname.strip().lower()
    if len(cleaned) < 3:
        return False
    return cleaned not in _GENERIC_HOSTNAMES


def match_device(
    observation: Observation, known_devices: list[KnownDevice]
) -> MatchResult:
    """Decide which known device (if any) this observation belongs to.

    Confidence semantics (matches the spec's own definitions):
      HIGH   - matched by a MAC previously confirmed stable for this device
      MEDIUM - matched by hostname only, or a MAC seen for the first time
               (Android/iOS both keep MACs stable per network by default,
               so a first sighting is a plausible future HIGH, not noise —
               but it isn't confirmed yet)
      LOW    - only an IP address was observed; nothing else to go on
    """
    mac_is_randomized = False
    normalized_mac: str | None = None

    if observation.mac:
        try:
            normalized_mac = normalize_mac(observation.mac)
            mac_is_randomized = is_locally_administered(normalized_mac)
        except InvalidMacAddressError:
            normalized_mac = None

    # 1. Exact MAC match against a known device -> HIGH confidence.
    if normalized_mac:
        for known in known_devices:
            if known.primary_mac and known.primary_mac.upper() == normalized_mac:
                return MatchResult(
                    device_id=known.device_id,
                    confidence=Confidence.HIGH,
                    reason=(
                        f"Matched existing device by MAC {normalized_mac}, "
                        "previously confirmed stable for this network"
                    ),
                    mac_is_randomized=mac_is_randomized,
                )

    # 2. Hostname match against a known device (MAC changed or absent) -> MEDIUM.
    if _is_specific_hostname(observation.hostname):
        for known in known_devices:
            if (
                known.last_hostname
                and known.last_hostname.strip().lower()
                == observation.hostname.strip().lower()  # type: ignore[union-attr]
            ):
                return MatchResult(
                    device_id=known.device_id,
                    confidence=Confidence.MEDIUM,
                    reason=(
                        f"MAC did not match, but hostname "
                        f"'{observation.hostname}' matches a known device — "
                        "treat with some caution"
                    ),
                    mac_is_randomized=mac_is_randomized,
                )

    # 2b. IP-adoption: the observation carries a MAC, and a known device
    # has no MAC yet but was last seen at this same IP (an IP-only
    # placeholder created by the DNS ingester for a never-scanned host).
    # Adopt the MAC into that record instead of duplicating the device.
    # Runs after the exact-MAC rule, so a MAC already claimed by another
    # device still matches its true owner first.
    if normalized_mac and observation.ip:
        for known in known_devices:
            if (
                known.primary_mac is None
                and known.last_ip
                and known.last_ip.strip() == observation.ip.strip()
            ):
                return MatchResult(
                    device_id=known.device_id,
                    confidence=Confidence.MEDIUM,
                    reason=(
                        f"MAC {normalized_mac} first seen at {observation.ip}, "
                        f"adopting it into IP-only device {known.device_id} — "
                        "treat with some caution until re-observed"
                    ),
                    mac_is_randomized=mac_is_randomized,
                )

    # 3. No match -> new device. Confidence reflects what we captured, not a guess.
    if normalized_mac:
        return MatchResult(
            device_id=None,
            confidence=Confidence.MEDIUM,
            reason=(
                f"New device: first observation of MAC {normalized_mac} "
                f"({'private/randomized' if mac_is_randomized else 'manufacturer-assigned'}). "
                "Will become HIGH confidence if this MAC is seen again on a later scan."
            ),
            mac_is_randomized=mac_is_randomized,
        )

    return MatchResult(
        device_id=None,
        confidence=Confidence.LOW,
        reason=(
            f"New device: only IP {observation.ip} was observed; "
            "MAC could not be resolved (ARP reply may still be pending)"
        ),
        mac_is_randomized=False,
    )
