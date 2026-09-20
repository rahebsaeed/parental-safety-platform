"""Phase 2 — dnsmasq query log parser.

Converts raw dnsmasq log lines into structured DnsLogEntry dataclasses.
Uses only the Python standard library; no external dependencies required.

dnsmasq log format (with `log-queries` enabled):
  query lines:
    Sep 12 21:00:01 dnsmasq[1234]: query[A] example.com from 192.168.1.10
    Sep 12 21:00:01 dnsmasq[1234]: query[AAAA] example.com from 192.168.1.10

  reply lines (one per answer; may be multiple for multi-A records):
    Sep 12 21:00:01 dnsmasq[1234]: reply example.com is 93.184.216.34
    Sep 12 21:00:01 dnsmasq[1234]: reply example.com is NODATA-IPv6
    Sep 12 21:00:01 dnsmasq[1234]: reply example.com is NXDOMAIN

  forwarding lines (not captured — noise):
    Sep 12 21:00:01 dnsmasq[1234]: forwarded example.com to 8.8.8.8

The parser is stateful: it buffers the most recent query line and merges
reply lines into it, because dnsmasq emits them as separate log events.

Design rules:
  - parse_line() NEVER raises — it returns None for any line it can't
    handle so the ingester's tail loop is never crashed by a noisy log.
  - All timestamps are returned as ISO-8601 UTC strings (the same format
    that storage.py always expects).
  - The current year is inferred from the system clock because dnsmasq
    log lines only include month+day, not year.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

# ── regex patterns ─────────────────────────────────────────────────────────────
#
# Examples matched:
#   Sep 12 21:00:01 dnsmasq[1234]: query[A] example.com from 192.168.1.10
#   12-Sep-2026 21:00:01 dnsmasq[1234]: query[A] example.com from 192.168.1.10
#
# dnsmasq can be compiled with or without the `--log-time` flag, which changes
# the date format.  We handle both the compact "Mon DD HH:MM:SS" (no-year) and
# the "DD-Mon-YYYY HH:MM:SS" (with-year) forms.
_TIMESTAMP_SHORT = r"(?P<ts_short>[A-Za-z]{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})"
_TIMESTAMP_LONG  = r"(?P<ts_long>\d{2}-[A-Za-z]{3}-\d{4}\s+\d{2}:\d{2}:\d{2})"
_PREFIX = rf"(?:{_TIMESTAMP_LONG}|{_TIMESTAMP_SHORT})\s+\S+\[[\d]+\]:\s+"

_QUERY_RE = re.compile(
    _PREFIX
    + r"query\[(?P<qtype>[A-Za-z0-9]+)\]\s+(?P<domain>\S+)\s+from\s+(?P<source_ip>\S+)"
)
_REPLY_RE = re.compile(
    _PREFIX + r"reply\s+(?P<domain>\S+)\s+is\s+(?P<answer>.+?)\s*$"
)

# Non-address answers (CNAME targets, MX exchanges, SRV targets, TXT
# snippets, PTR names) are kept as short text so those query types stay
# inspectable instead of storing an empty answer.
_MAX_ANSWER_TEXT = 255
_NXDOMAIN_RE = re.compile(
    _PREFIX + r"(?P<status>NXDOMAIN|SERVFAIL|REFUSED)\s+(?P<domain>\S+)"
)


@dataclass
class DnsLogEntry:
    """One complete DNS transaction: a query + its replies (if any)."""

    occurred_at: str        # ISO-8601 UTC
    source_ip: str
    domain: str
    query_type: str
    response_status: str = "NOERROR"
    resolved_addresses: list[str] = field(default_factory=list)

    @property
    def resolved_addresses_str(self) -> str | None:
        """Comma-separated addresses for storage, or None if empty."""
        return ",".join(self.resolved_addresses) if self.resolved_addresses else None


def _parse_timestamp(match: re.Match) -> str:
    """Convert a regex match's timestamp groups to ISO-8601 UTC string.

    Returns an ISO-8601 string on success, or a fallback using the current
    time if parsing fails (so the ingester never crashes on a bad timestamp).
    """
    ts_long = match.group("ts_long")
    ts_short = match.group("ts_short")
    now = datetime.now(timezone.utc)
    try:
        if ts_long:
            # dnsmasq logs in the host's local timezone, not UTC.
            dt = datetime.strptime(ts_long, "%d-%b-%Y %H:%M:%S").astimezone(
                timezone.utc
            )
        else:
            # Short form has no year — use current year, correct for Dec→Jan wrap.
            # Naive strptime is local time; convert to UTC for storage.
            dt = datetime.strptime(
                f"{now.year} {ts_short}", "%Y %b %d %H:%M:%S"
            ).astimezone(timezone.utc)
            # If the parsed date is in the future by more than a day, it's
            # probably last year (log from late December, parsed in January).
            if (dt - now).total_seconds() > 86400:
                dt = dt.replace(year=now.year - 1)
    except ValueError:
        dt = now
    return dt.isoformat()


class LogParser:
    """Stateful parser that pairs query lines with their reply lines.

    dnsmasq emits a `query[…]` line immediately followed by one or more
    `reply` lines (or a NXDOMAIN/SERVFAIL line).  The parser buffers the
    most recent query and flushes it as a complete DnsLogEntry when:
      - a new query line arrives (flush the previous one first), or
      - a reply/error line that matches the buffered query's domain arrives.

    Call parse_line() for each log line in order.  It returns a complete
    DnsLogEntry when one is ready, or None while buffering.
    Call flush() at end-of-file to emit any buffered incomplete entry.
    """

    def __init__(self) -> None:
        self._pending: DnsLogEntry | None = None

    def parse_line(self, line: str) -> DnsLogEntry | None:
        """Process one log line. Returns a complete entry or None."""
        line = line.strip()
        if not line:
            return None

        # ── query line ──────────────────────────────────────────────────────
        m = _QUERY_RE.search(line)
        if m:
            completed = self._pending  # flush previous if any
            self._pending = DnsLogEntry(
                occurred_at=_parse_timestamp(m),
                source_ip=m.group("source_ip"),
                domain=m.group("domain").rstrip("."),
                query_type=m.group("qtype").upper(),
            )
            return completed  # may be None if this is the very first query

        # ── reply line ──────────────────────────────────────────────────────
        m = _REPLY_RE.search(line)
        if m and self._pending:
            answer = m.group("answer").strip().strip('"')
            domain = m.group("domain").rstrip(".")
            if domain == self._pending.domain:
                if answer.upper() in ("NXDOMAIN", "NODATA", "NODATA-IPV4", "NODATA-IPV6"):
                    self._pending.response_status = "NXDOMAIN"
                elif re.match(r"^\d+\.\d+\.\d+\.\d+$", answer) or (
                    ":" in answer and re.match(r"^[0-9a-fA-F:.]+$", answer)
                ):
                    # IPv4 address, or IPv6 address (hex/colons only — a TXT
                    # record containing ':' plus other text falls through
                    # to the text branch below).
                    self._pending.resolved_addresses.append(answer)
                elif answer:
                    # CNAME / MX / SRV / TXT / PTR answer text (truncated).
                    self._pending.resolved_addresses.append(answer[:_MAX_ANSWER_TEXT])
            return None

        # ── inline NXDOMAIN/SERVFAIL line ───────────────────────────────────
        m = _NXDOMAIN_RE.search(line)
        if m and self._pending:
            domain = m.group("domain").rstrip(".")
            if domain == self._pending.domain:
                self._pending.response_status = m.group("status")
            return None

        return None

    def flush(self) -> DnsLogEntry | None:
        """Return and clear any buffered incomplete entry (call at EOF)."""
        entry = self._pending
        self._pending = None
        return entry


def parse_lines(lines: list[str]) -> list[DnsLogEntry]:
    """Convenience wrapper: parse a list of log lines and return all
    complete entries.  Suitable for unit tests and one-shot file ingestion.
    """
    parser = LogParser()
    results: list[DnsLogEntry] = []
    for line in lines:
        entry = parser.parse_line(line)
        if entry is not None:
            results.append(entry)
    final = parser.flush()
    if final is not None:
        results.append(final)
    return results
