"""MAC address classification: locally-administered (private/randomized)
detection, and optional vendor lookup against a real IEEE OUI file.

Deliberately contains no hand-written OUI-prefix-to-vendor table. See
docs/architecture/phase-1-discovery.md ("Why no hand-written MAC vendor
table") — a table typed from memory can't be guaranteed correct, and a
wrong vendor guess in a monitoring tool is worse than an honest "unknown".

Get the real registry (public domain) at:
    https://standards-oui.ieee.org/oui/oui.txt
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}$")

# The IEEE oui.txt format lists each OUI twice per entry — once dashed
# ("00-1A-2B   (hex)") and once contiguous ("001A2B     (base 16)"). This
# matches the contiguous "(base 16)" line, since that's already in the
# exact format used as this module's dict keys.
_OUI_LINE_RE = re.compile(
    r"^([0-9A-Fa-f]{6})\s+\(base 16\)\s+(.+?)\s*$", re.MULTILINE
)


class InvalidMacAddressError(ValueError):
    pass


@dataclass(frozen=True)
class MacInfo:
    mac: str
    is_locally_administered: bool
    vendor: str | None  # None if no OUI database was loaded and MAC isn't randomized


def normalize_mac(mac: str) -> str:
    """Normalize to uppercase colon-separated form. Raises
    InvalidMacAddressError on malformed input rather than guessing.
    """
    if not _MAC_RE.match(mac):
        raise InvalidMacAddressError(f"Not a MAC address: {mac!r}")
    return mac.upper().replace("-", ":")


def is_locally_administered(mac: str) -> bool:
    """True if the MAC's U/L bit is set, i.e. it is NOT a globally-unique
    IEEE-assigned address (locally-administered addresses are what
    Android/iOS MAC randomization produces). This is a bit-flag check
    against the first octet, not a lookup table, so it's exact by
    construction.
    """
    normalized = normalize_mac(mac)
    first_octet = int(normalized.split(":")[0], 16)
    return bool(first_octet & 0b0000_0010)


def load_oui_database(path: str) -> dict[str, str]:
    """Parse a real IEEE oui.txt file into {OUI_PREFIX (6 hex chars,
    uppercase, no separators): vendor_name}.

    Raises FileNotFoundError / OSError naturally if the path is bad —
    callers should treat a missing database as "vendor lookup
    unavailable", not fall back to guessing.
    """
    with open(path, encoding="utf-8", errors="replace") as fh:
        contents = fh.read()

    database: dict[str, str] = {}
    for match in _OUI_LINE_RE.finditer(contents):
        prefix, vendor = match.group(1).upper(), match.group(2).strip()
        database[prefix] = vendor
    return database


def describe(mac: str, oui_database: dict[str, str] | None = None) -> MacInfo:
    """Classify a MAC address. Never invents a vendor name: if
    oui_database is None (or the prefix isn't in it), vendor is None and
    callers should display that as "Unknown", not blank or a guess.
    """
    normalized = normalize_mac(mac)
    randomized = is_locally_administered(normalized)

    vendor: str | None = None
    if not randomized and oui_database:
        prefix = normalized.replace(":", "")[:6]
        vendor = oui_database.get(prefix)

    return MacInfo(mac=normalized, is_locally_administered=randomized, vendor=vendor)
