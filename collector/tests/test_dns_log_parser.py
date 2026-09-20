"""Tests for collector.dns.log_parser.

These tests are unit-level: no filesystem, no database, no network.
Every test uses hard-coded log line strings in the format dnsmasq 2.90
actually emits (confirmed by the running instance on the development host).
"""

from __future__ import annotations

import pytest

from collector.dns.log_parser import DnsLogEntry, LogParser, parse_lines


# ── helpers ────────────────────────────────────────────────────────────────────

def _query(qtype: str, domain: str, source_ip: str) -> str:
    return f"Sep 12 21:00:01 dnsmasq[1234]: query[{qtype}] {domain} from {source_ip}"


def _reply(domain: str, answer: str) -> str:
    return f"Sep 12 21:00:01 dnsmasq[1234]: reply {domain} is {answer}"


def _cached(domain: str, answer: str) -> str:
    # dnsmasq emits 'cached' instead of 'reply' for cache hits — we treat
    # these the same way (ignored, not crashing).
    return f"Sep 12 21:00:01 dnsmasq[1234]: cached {domain} is {answer}"


def _forwarded(domain: str, server: str) -> str:
    return f"Sep 12 21:00:01 dnsmasq[1234]: forwarded {domain} to {server}"


# ── basic query + reply ────────────────────────────────────────────────────────

class TestBasicQueryReply:
    def test_single_a_query_with_ip_reply(self):
        lines = [
            _query("A", "example.com", "192.168.1.10"),
            _reply("example.com", "93.184.216.34"),
            # A second query flushes the first
            _query("A", "other.com", "192.168.1.10"),
        ]
        entries = parse_lines(lines)
        assert len(entries) == 2
        first = entries[0]
        assert first.domain == "example.com"
        assert first.query_type == "A"
        assert first.source_ip == "192.168.1.10"
        assert first.response_status == "NOERROR"
        assert "93.184.216.34" in first.resolved_addresses

    def test_aaaa_query(self):
        lines = [
            _query("AAAA", "example.com", "192.168.1.10"),
            _reply("example.com", "2606:2800:220:1:248:1893:25c8:1946"),
            _query("A", "done.com", "192.168.1.10"),
        ]
        entries = parse_lines(lines)
        first = entries[0]
        assert first.query_type == "AAAA"
        assert "2606:2800:220:1:248:1893:25c8:1946" in first.resolved_addresses

    def test_multiple_a_records_in_reply(self):
        """A record with multiple IPs (e.g. CDN round-robin)."""
        lines = [
            _query("A", "multi.example.com", "192.168.1.5"),
            _reply("multi.example.com", "1.2.3.4"),
            _reply("multi.example.com", "5.6.7.8"),
            _reply("multi.example.com", "9.10.11.12"),
            _query("A", "flush.com", "192.168.1.5"),
        ]
        entries = parse_lines(lines)
        assert len(entries[0].resolved_addresses) == 3
        assert "1.2.3.4" in entries[0].resolved_addresses
        assert "9.10.11.12" in entries[0].resolved_addresses

    def test_resolved_addresses_str_comma_separated(self):
        lines = [
            _query("A", "cdn.example.com", "192.168.1.1"),
            _reply("cdn.example.com", "10.0.0.1"),
            _reply("cdn.example.com", "10.0.0.2"),
            _query("A", "x.com", "192.168.1.1"),
        ]
        entry = parse_lines(lines)[0]
        assert entry.resolved_addresses_str == "10.0.0.1,10.0.0.2"

    def test_no_reply_lines_resolved_addresses_str_is_none(self):
        lines = [_query("A", "example.com", "192.168.1.1")]
        entry = parse_lines(lines)[0]
        assert entry.resolved_addresses_str is None


# ── NXDOMAIN / error responses ─────────────────────────────────────────────────

class TestErrorResponses:
    def test_nxdomain_via_reply_line(self):
        lines = [
            _query("A", "does-not-exist.invalid", "192.168.1.10"),
            _reply("does-not-exist.invalid", "NXDOMAIN"),
            _query("A", "flush.com", "192.168.1.10"),
        ]
        entries = parse_lines(lines)
        assert entries[0].response_status == "NXDOMAIN"

    def test_nodata_ipv6_is_treated_as_nxdomain(self):
        lines = [
            _query("AAAA", "ipv4only.example.com", "192.168.1.10"),
            _reply("ipv4only.example.com", "NODATA-IPv6"),
            _query("A", "flush.com", "192.168.1.10"),
        ]
        entries = parse_lines(lines)
        assert entries[0].response_status == "NXDOMAIN"

    def test_nodata_ipv4(self):
        lines = [
            _query("A", "ipv6only.example.com", "192.168.1.10"),
            _reply("ipv6only.example.com", "NODATA"),
            _query("A", "flush.com", "192.168.1.10"),
        ]
        entries = parse_lines(lines)
        assert entries[0].response_status == "NXDOMAIN"


# ── different source IPs ───────────────────────────────────────────────────────

class TestMultipleSourceIPs:
    def test_queries_from_different_devices_are_independent(self):
        lines = [
            _query("A", "apple.com", "192.168.1.10"),
            _reply("apple.com", "17.253.144.10"),
            _query("A", "google.com", "192.168.1.20"),
            _reply("google.com", "142.250.80.46"),
            _query("A", "flush.com", "192.168.1.1"),
        ]
        entries = parse_lines(lines)
        assert entries[0].source_ip == "192.168.1.10"
        assert entries[0].domain == "apple.com"
        assert entries[1].source_ip == "192.168.1.20"
        assert entries[1].domain == "google.com"


# ── malformed / irrelevant lines ──────────────────────────────────────────────

class TestMalformedLines:
    def test_forwarded_line_produces_no_entry(self):
        lines = [_forwarded("example.com", "8.8.8.8")]
        assert parse_lines(lines) == []

    def test_cached_line_produces_no_entry(self):
        lines = [_cached("example.com", "93.184.216.34")]
        assert parse_lines(lines) == []

    def test_empty_line_produces_no_entry(self):
        assert parse_lines([""]) == []
        assert parse_lines(["   \n"]) == []

    def test_completely_random_text_produces_no_entry(self):
        assert parse_lines(["this is not a dnsmasq log line at all"]) == []

    def test_parser_does_not_raise_on_garbage(self):
        """parse_line must never raise, regardless of input."""
        parser = LogParser()
        parser.parse_line("SELECT * FROM users; DROP TABLE users; --")
        parser.parse_line("\x00\x01\x02")
        parser.parse_line("A" * 10_000)


# ── trailing dot stripping ─────────────────────────────────────────────────────

class TestTrailingDot:
    def test_trailing_dot_stripped_from_domain(self):
        lines = [
            "Sep 12 21:00:01 dnsmasq[1234]: query[A] example.com. from 192.168.1.10",
            _query("A", "flush.com", "192.168.1.1"),
        ]
        entries = parse_lines(lines)
        assert entries[0].domain == "example.com"


# ── timestamp handling ─────────────────────────────────────────────────────────

class TestTimestamps:
    def test_short_timestamp_parses_to_iso(self):
        lines = [_query("A", "example.com", "192.168.1.1")]
        entry = parse_lines(lines)[0]
        # Must be a valid ISO-8601 string ending in +00:00
        assert "T" in entry.occurred_at
        assert entry.occurred_at.endswith("+00:00")

    def test_long_timestamp_format(self):
        """Test the DD-Mon-YYYY HH:MM:SS format."""
        lines = [
            "12-Sep-2026 21:00:01 dnsmasq[1234]: query[A] example.com from 192.168.1.10",
        ]
        entry = parse_lines(lines)[0]
        assert "2026-09-12" in entry.occurred_at

    def test_log_timestamps_are_interpreted_as_local_time(self):
        """dnsmasq logs in host-local time; occurred_at must be the same
        instant in UTC, not the wall-clock stamped +00:00 (which put every
        query an hour in the future on UTC+1 hosts)."""
        from datetime import datetime, timezone

        now_local = datetime.now().astimezone()
        stamp = now_local.strftime("%d-%b-%Y %H:%M:%S")
        lines = [
            f"{stamp} dnsmasq[1234]: query[A] example.com from 192.168.1.10",
        ]
        entry = parse_lines(lines)[0]
        parsed = datetime.fromisoformat(entry.occurred_at)
        assert abs((parsed - datetime.now(timezone.utc)).total_seconds()) < 120


# ── stateful parser flush ──────────────────────────────────────────────────────

class TestParserFlush:
    def test_flush_returns_pending_entry(self):
        parser = LogParser()
        parser.parse_line(_query("A", "example.com", "192.168.1.1"))
        parser.parse_line(_reply("example.com", "1.2.3.4"))
        entry = parser.flush()
        assert entry is not None
        assert entry.domain == "example.com"
        assert "1.2.3.4" in entry.resolved_addresses

    def test_flush_returns_none_when_nothing_pending(self):
        parser = LogParser()
        assert parser.flush() is None

    def test_flush_clears_state(self):
        parser = LogParser()
        parser.parse_line(_query("A", "example.com", "192.168.1.1"))
        parser.flush()
        assert parser.flush() is None


# ── non-address answers (CNAME / MX / SRV / TXT / PTR) ────────────────────────

class TestNonAddressAnswers:
    def test_cname_target_is_kept(self):
        entries = parse_lines([
            _query("CNAME", "alias.example.com", "192.168.1.10"),
            _reply("alias.example.com", "canonical.example.net"),
            _query("A", "done.com", "192.168.1.10"),
        ])
        assert entries[0].query_type == "CNAME"
        assert entries[0].resolved_addresses == ["canonical.example.net"]

    def test_mx_exchange_is_kept(self):
        entries = parse_lines([
            _query("MX", "example.com", "192.168.1.10"),
            _reply("example.com", "10 mail.example.com"),
            _query("A", "done.com", "192.168.1.10"),
        ])
        assert entries[0].resolved_addresses == ["10 mail.example.com"]

    def test_txt_with_colon_is_text_not_ipv6(self):
        entries = parse_lines([
            _query("TXT", "example.com", "192.168.1.10"),
            _reply("example.com", "v=spf1 ip4:1.2.3.4 -all"),
            _query("A", "done.com", "192.168.1.10"),
        ])
        assert entries[0].resolved_addresses == ["v=spf1 ip4:1.2.3.4 -all"]

    def test_ipv6_reply_still_recognized(self):
        entries = parse_lines([
            _query("AAAA", "example.com", "192.168.1.10"),
            _reply("example.com", "2606:2800:220:1:248:1893:25c8:1946"),
            _query("A", "done.com", "192.168.1.10"),
        ])
        assert entries[0].resolved_addresses == ["2606:2800:220:1:248:1893:25c8:1946"]

    def test_long_txt_answer_is_truncated(self):
        long_text = "x" * 400
        entries = parse_lines([
            _query("TXT", "example.com", "192.168.1.10"),
            _reply("example.com", long_text),
            _query("A", "done.com", "192.168.1.10"),
        ])
        assert len(entries[0].resolved_addresses[0]) == 255
