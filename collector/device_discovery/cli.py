"""Command-line entry point for Phase 1.

    parental-monitor-discover scan
    parental-monitor-discover list
    parental-monitor-discover rename dev_01 "Samsung Phone"
    parental-monitor-discover classify dev_01 Android
    parental-monitor-discover history dev_01
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from collector.device_discovery import discovery_service, logging_utils, mac_vendor, storage
from collector.device_discovery.network_info import NetworkDetectionError, detect_network_info

DEFAULT_DB_PATH = "./data/discovery.sqlite3"

logger = logging.getLogger(__name__)


def _db_path(args: argparse.Namespace) -> str:
    return args.db_path or os.environ.get("DISCOVERY_DB_PATH", DEFAULT_DB_PATH)


def _fix_ownership_if_root_via_sudo(db_path: str) -> None:
    """If this process is running as root because of `sudo` (which Phase 1
    needs for the active ARP scan), chown the database file and its parent
    directory back to the invoking user.

    Without this, `sudo ... scan` creates data/discovery.sqlite3 owned by
    root, and a later plain `python ... scan` — passive-only discovery
    without sudo, an explicitly supported mode — fails with
    "attempt to write a readonly database" instead of working. `list`,
    `rename`, `classify`, and `history` go through the same path in case
    someone runs one of those under sudo too.
    """
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None or geteuid() != 0:
        return  # not root; nothing to fix

    sudo_uid = os.environ.get("SUDO_UID")
    sudo_gid = os.environ.get("SUDO_GID")
    if not sudo_uid or not sudo_gid:
        return  # genuinely running as root (not via sudo) — leave ownership as-is

    uid, gid = int(sudo_uid), int(sudo_gid)
    path = Path(db_path)
    try:
        if path.exists():
            os.chown(path, uid, gid)
        if path.parent.exists():
            os.chown(path.parent, uid, gid)
    except OSError as exc:
        logger.warning(
            "Could not fix ownership of %s (%s). You may need to run: "
            "sudo chown -R $USER:$USER %s",
            db_path,
            exc,
            path.parent,
        )


def _open_db(args: argparse.Namespace) -> sqlite3.Connection:
    db_path = _db_path(args)
    conn = storage.init_db(db_path)
    _fix_ownership_if_root_via_sudo(db_path)
    return conn


def _local_time(iso_utc: str) -> str:
    try:
        return datetime.fromisoformat(iso_utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return iso_utc


def _truncate(text: str, max_len: int = 22) -> str:
    return text if len(text) <= max_len else text[: max_len - 1] + "…"


def _format_devices_table(devices: list[storage.DeviceRecord]) -> str:
    if not devices:
        return "No devices recorded yet. Run `scan` first."

    headers = ["DEVICE ID", "NAME", "TYPE", "MAC", "VENDOR", "STATUS", "CONFIDENCE", "LAST SEEN"]
    rows = [
        [
            d.device_id,
            d.friendly_name or "(unnamed)",
            d.device_type or "(unclassified)",
            d.primary_mac or "(unknown)",
            _truncate(d.vendor or "(unknown)"),
            d.status.upper(),
            d.confidence,
            _local_time(d.last_seen),
        ]
        for d in devices
    ]
    widths = [
        max(len(headers[i]), *(len(row[i]) for row in rows)) for i in range(len(headers))
    ]
    lines = [
        "  ".join(h.ljust(w) for h, w in zip(headers, widths)),
        "  ".join("-" * w for w in widths),
    ]
    lines.extend("  ".join(c.ljust(w) for c, w in zip(row, widths)) for row in rows)
    return "\n".join(lines)


def _has_raw_socket_capability() -> bool:
    """Check for CAP_NET_RAW without requiring root uid.

    Systemd services (parental-monitor-api / collector) run as the
    unprivileged `parental-monitor` user but with
    AmbientCapabilities=CAP_NET_RAW CAP_NET_ADMIN, so `geteuid() == 0`
    is the wrong gate for "can we do an active ARP scan". Try opening
    a raw socket: success means the active scan is worth attempting;
    PermissionError means fall back to passive-only.
    """
    try:
        import socket  # noqa: PLC0415 (local import keeps CLI startup light)
    except Exception:
        return False
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except PermissionError:
        return False
    except OSError:
        # Any other OS error (e.g. protocol unsupported) still tells us
        # nothing about privileges — be conservative and say no.
        return False
    else:
        try:
            s.close()
        except Exception:
            pass
        return True


def _can_attempt_active_scan() -> bool:
    geteuid = getattr(os, "geteuid", None)
    if geteuid is None:
        return True  # non-POSIX (Windows dev) — let discover_hosts try/fallback
    if geteuid() == 0:
        return True
    return _has_raw_socket_capability()


def cmd_scan(args: argparse.Namespace) -> int:
    logging_utils.configure_logging(os.environ.get("LOG_LEVEL", "INFO"))

    interface_override = args.interface or os.environ.get("DISCOVERY_INTERFACE")
    try:
        network = detect_network_info(preferred_interface=interface_override)
    except NetworkDetectionError as exc:
        print(f"Could not determine network topology: {exc}", file=sys.stderr)
        return 1

    oui_database = None
    # Auto-load OUI database if it exists
    import os as _os
    _oui_path = _os.environ.get("OUI_FILE", "/opt/parental-safety/collector/device_discovery/oui/oui.txt")
    if _os.path.exists(_oui_path):
        try:
            oui_database = mac_vendor.load_oui_database(_oui_path)
        except OSError:
            pass
    if args.oui_file:
        try:
            oui_database = mac_vendor.load_oui_database(args.oui_file)
        except OSError as exc:
            print(f"Warning: could not load OUI file '{args.oui_file}': {exc}", file=sys.stderr)

    attempt_active = _can_attempt_active_scan()
    if not attempt_active:
        print(
            "Not running as root/sudo: falling back to passive-only discovery "
            "(reduced visibility — see docs/architecture/phase-1-discovery.md).",
            file=sys.stderr,
        )

    conn = _open_db(args)
    try:
        summary = discovery_service.run_discovery_cycle(
            conn, network, attempt_active=attempt_active, oui_database=oui_database
        )
    finally:
        conn.close()

    print(
        f"Interface: {summary.network.interface}  "
        f"Subnet: {summary.network.subnet_cidr}  "
        f"Gateway: {summary.network.gateway_ip or '(unknown)'}"
    )
    if summary.active_scan_attempted and not summary.active_scan_succeeded:
        print(
            f"NOTE: active scan unavailable ({summary.unavailable_reason}); "
            "results are passive-only and may be incomplete."
        )
    print()
    print(_format_devices_table(summary.devices))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    conn = _open_db(args)
    try:
        devices = storage.get_all_devices(conn)
    finally:
        conn.close()
    print(_format_devices_table(devices))
    return 0


def cmd_rename(args: argparse.Namespace) -> int:
    conn = _open_db(args)
    try:
        ok = storage.set_friendly_name(conn, args.device_id, args.name)
    finally:
        conn.close()
    if not ok:
        print(f"No such device: {args.device_id}", file=sys.stderr)
        return 1
    print(f"{args.device_id} renamed to '{args.name}'")
    return 0


def cmd_classify(args: argparse.Namespace) -> int:
    conn = _open_db(args)
    try:
        ok = storage.set_device_type(conn, args.device_id, args.device_type)
    finally:
        conn.close()
    if not ok:
        print(f"No such device: {args.device_id}", file=sys.stderr)
        return 1
    print(f"{args.device_id} classified as '{args.device_type}'")
    return 0


def cmd_history(args: argparse.Namespace) -> int:
    conn = _open_db(args)
    try:
        device = storage.get_device(conn, args.device_id)
        if device is None:
            print(f"No such device: {args.device_id}", file=sys.stderr)
            return 1
        history = storage.get_ip_history(conn, args.device_id, limit=args.limit)
    finally:
        conn.close()

    label = device.friendly_name or device.device_id
    print(f"IP history for {label} ({device.device_id}):")
    if not history:
        print("  (no history yet)")
        return 0
    for entry in history:
        print(
            f"  {_local_time(entry.observed_at)}  {entry.ip_address:<15}  "
            f"mac={entry.mac_address or '(unknown)'}  "
            f"vendor={entry.vendor or '(unknown)'}  "
            f"host={entry.hostname or '(none)'}"
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="parental-monitor-discover", description="Phase 1: LAN device discovery"
    )
    parser.add_argument(
        "--db-path",
        default=None,
        help="Override the SQLite store path "
        "(default: DISCOVERY_DB_PATH env var, or ./data/discovery.sqlite3)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="Run a discovery scan and display results")
    p_scan.add_argument("--interface", default=None, help="Override auto-detected interface")
    p_scan.add_argument(
        "--oui-file", default=None, help="Path to a real IEEE oui.txt file for vendor lookups"
    )
    p_scan.set_defaults(func=cmd_scan)

    p_list = sub.add_parser("list", help="Display known devices without scanning")
    p_list.set_defaults(func=cmd_list)

    p_rename = sub.add_parser("rename", help="Set a device's friendly name")
    p_rename.add_argument("device_id")
    p_rename.add_argument("name")
    p_rename.set_defaults(func=cmd_rename)

    p_classify = sub.add_parser("classify", help="Set a device's type")
    p_classify.add_argument("device_id")
    p_classify.add_argument("device_type")
    p_classify.set_defaults(func=cmd_classify)

    p_history = sub.add_parser("history", help="Show IP history for a device")
    p_history.add_argument("device_id")
    p_history.add_argument("--limit", type=int, default=50)
    p_history.set_defaults(func=cmd_history)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
