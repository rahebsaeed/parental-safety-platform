"""Phase 2 — DNS observation CLI.

    parental-monitor-dns start    # start the log ingester loop
    parental-monitor-dns tail     # show last N DNS queries from the database
    parental-monitor-dns status   # per-device DNS visibility summary
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from collector.device_discovery import logging_utils, storage
from collector.dns.ingester import Ingester

DEFAULT_DB_PATH = "./data/discovery.sqlite3"
DEFAULT_LOG_PATH = "/var/log/parental-safety/dnsmasq.log"

logger = logging.getLogger(__name__)


def _db_path(args: argparse.Namespace) -> str:
    return args.db_path or os.environ.get("DISCOVERY_DB_PATH", DEFAULT_DB_PATH)


def _log_path(args: argparse.Namespace) -> str:
    return args.log_path or os.environ.get("DNS_LOG_PATH", DEFAULT_LOG_PATH)


def _local_time(iso_utc: str) -> str:
    from datetime import datetime

    try:
        return datetime.fromisoformat(iso_utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return iso_utc


def _truncate(text: str, max_len: int = 40) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


# ── commands ───────────────────────────────────────────────────────────────────


def cmd_start(args: argparse.Namespace) -> int:
    logging_utils.configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
    db = _db_path(args)
    log = _log_path(args)

    if not os.path.exists(log):
        print(
            f"Warning: log file not found at {log}\n"
            "Start dnsmasq first:  sudo bash infrastructure/dnsmasq/setup.sh start",
            file=sys.stderr,
        )
        # Don't exit — the log file may appear shortly.

    ingester = Ingester(
        log_path=log,
        db_path=db,
        poll_interval=args.poll_interval,
    )
    print(f"DNS ingester running. Watching {log} → {db}")
    print("Press Ctrl+C to stop.")
    ingester.run_forever()
    return 0


def cmd_tail(args: argparse.Namespace) -> int:
    conn = storage.init_db(_db_path(args))
    try:
        queries = storage.get_recent_dns_queries(conn, limit=args.limit)
    finally:
        conn.close()

    if not queries:
        print("No DNS queries recorded yet. Is the ingester running?")
        return 0

    headers = ["TIME", "DEVICE", "SOURCE IP", "DOMAIN", "TYPE", "STATUS", "VISIBILITY"]
    rows = [
        [
            _local_time(q.occurred_at),
            q.device_id or "(unknown)",
            q.source_ip,
            _truncate(q.domain),
            q.query_type,
            q.response_status,
            q.dns_visibility,
        ]
        for q in queries
    ]
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))
    ]
    lines = [
        "  ".join(h.ljust(w) for h, w in zip(headers, widths)),
        "  ".join("-" * w for w in widths),
    ]
    lines.extend("  ".join(c.ljust(w) for c, w in zip(row, widths)) for row in rows)
    print("\n".join(lines))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    conn = storage.init_db(_db_path(args))
    try:
        summary = storage.get_dns_visibility_summary(conn)
        devices = {d.device_id: d for d in storage.get_all_devices(conn)}
    finally:
        conn.close()

    if not summary:
        print("No DNS queries recorded yet. Is the ingester running?")
        return 0

    print("DNS Visibility Summary")
    print("─" * 65)
    print(f"{'DEVICE':<12}  {'NAME':<22}  {'QUERIES':>8}  {'PARTIAL':>8}  STATUS")
    print("─" * 65)
    for row in summary:
        device_id = row["device_id"] or "(unknown)"
        total = row["total_queries"]
        partial = row["partial_queries"] or 0
        device = devices.get(device_id)
        name = (device.friendly_name or "(unnamed)") if device else "(not in DB)"
        # Show a warning flag if there are PARTIAL queries (DoH/DoT bypass)
        flag = " ⚠️  DoH/DoT bypass suspected" if partial > 0 else ""
        print(f"{device_id:<12}  {name[:22]:<22}  {total:>8}  {partial:>8}{flag}")
    print("─" * 65)
    print(
        "\nPARTIAL = queries from an IP not in the Phase 1 device table.\n"
        "This typically means the device is using DNS-over-HTTPS or a\n"
        "private DNS provider, bypassing this resolver.\n"
        "Phase 1 'scan' may also not have seen the device yet."
    )
    return 0


# ── parser ─────────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parental-monitor-dns", description="Phase 2: DNS observation"
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="SQLite store path (default: DISCOVERY_DB_PATH env or ./data/discovery.sqlite3)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start the DNS log ingester loop")
    p_start.add_argument(
        "--log-path",
        default=None,
        help=f"dnsmasq log file to watch (default: DNS_LOG_PATH env or {DEFAULT_LOG_PATH})",
    )
    p_start.add_argument(
        "--poll-interval",
        type=int,
        default=5,
        help="Seconds between log polls (default: 5)",
    )
    p_start.set_defaults(func=cmd_start)

    p_tail = sub.add_parser("tail", help="Show recent DNS queries from the database")
    p_tail.add_argument("--limit", type=int, default=50, help="Max rows to show (default: 50)")
    p_tail.set_defaults(func=cmd_tail)

    p_status = sub.add_parser("status", help="Per-device DNS visibility summary")
    p_status.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
