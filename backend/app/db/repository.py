from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

from backend.app.core.config import settings
from backend.app.schemas.devices import (
    DeviceSummary,
    DeviceDetail,
    DeviceAddressItem,
    DeviceStatusEventItem,
)
from backend.app.schemas.activity import DnsQueryItem
from backend.app.schemas.domains import TopDomainItem, DnsStatsResponse
from backend.app.schemas.health import HealthResponse

# A device whose last_seen is older than this is reported as offline,
# even if its stored status row still says 'online'. Discovery scans run
# on demand (Scan button) — between scans the DB row goes stale, and the
# old code kept showing everything as online forever. 30 minutes matches
# a typical home-LAN DHCP/presence window.
OFFLINE_AFTER_MINUTES = 120


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _detect_gateway_ip() -> str | None:
    """Return this host's LAN default-gateway IP, or None if undetectable.

    Used to flag the router itself (is_gateway) so the online device list
    mirrors the router's own connected-client count, which never includes
    itself. Lazy import keeps the collector package out of backend import
    time; any failure degrades to None (no exclusion, no flag) rather than
    breaking the device list.
    """
    try:
        from collector.device_discovery.network_info import (  # noqa: PLC0415
            detect_network_info,
        )

        return detect_network_info().gateway_ip
    except Exception:
        return None


def _effective_status(stored_status: str, last_seen_iso: str | None) -> str:
    """Return 'online' only if the device was seen recently."""
    if (stored_status or "").lower() != "online":
        return "offline"
    last_seen = _parse_iso(last_seen_iso)
    if last_seen is None:
        return stored_status or "offline"
    age = datetime.now(timezone.utc) - last_seen.astimezone(timezone.utc)
    if age.total_seconds() > OFFLINE_AFTER_MINUTES * 60:
        return "offline"
    return "online"


class Repository:
    """Data access layer for device discovery and DNS monitoring data."""

    # ── Devices ───────────────────────────────────────────────────────────────

    @staticmethod
    def list_devices(
        conn: sqlite3.Connection,
        status_filter: Optional[str] = None,
    ) -> list[DeviceSummary]:
        """List all devices with latest IP, query count, and DNS visibility status."""
        query = """
            SELECT
                d.device_id,
                d.friendly_name,
                d.device_type,
                d.primary_mac,
                d.mac_is_randomized,
                d.vendor,
                d.status,
                d.confidence,
                d.first_seen,
                d.last_seen,
                (
                    SELECT ip_address
                    FROM device_addresses da
                    WHERE da.device_id = d.device_id
                      AND INSTR(da.ip_address, '.') > 0
                    ORDER BY observed_at DESC, id DESC
                    LIMIT 1
                ) AS current_ip,
                (
                    SELECT COUNT(*)
                    FROM dns_queries q
                    WHERE q.device_id = d.device_id
                ) AS query_count,
                (
                    SELECT COUNT(*)
                    FROM dns_queries q
                    WHERE q.device_id = d.device_id AND q.dns_visibility = 'PARTIAL'
                ) AS partial_query_count
            FROM devices d
        """
        # NOTE: status filtering happens in Python after _effective_status()
        # is applied, because the stored d.status row goes stale between
        # scans. Filtering in SQL on d.status would hide the offline
        # transition.
        query += " ORDER BY d.last_seen DESC;"

        rows = conn.execute(query, []).fetchall()
        gateway_ip = _detect_gateway_ip()
        devices = []
        for r in rows:
            q_count = r["query_count"] or 0
            p_count = r["partial_query_count"] or 0

            # Determine visibility flag
            if q_count == 0:
                visibility = "NONE"
            elif p_count > 0:
                visibility = "PARTIAL"
            else:
                visibility = "FULL"

            effective = _effective_status(r["status"], r["last_seen"])
            if status_filter and effective != status_filter.lower():
                continue

            is_gateway = bool(gateway_ip and r["current_ip"] == gateway_ip)
            if is_gateway and (status_filter or "").lower() == "online":
                # The router never counts itself among connected clients —
                # neither do we in the online view. It stays visible under
                # the unfiltered list and keeps its DB record for DNS
                # attribution.
                continue

            devices.append(
                DeviceSummary(
                    device_id=r["device_id"],
                    friendly_name=r["friendly_name"],
                    device_type=r["device_type"],
                    primary_mac=r["primary_mac"],
                    mac_is_randomized=bool(r["mac_is_randomized"]),
                    vendor=r["vendor"],
                    status=effective,
                    confidence=r["confidence"],
                    first_seen=r["first_seen"],
                    last_seen=r["last_seen"],
                    current_ip=r["current_ip"],
                    query_count=q_count,
                    dns_visibility=visibility,
                    is_gateway=is_gateway,
                )
            )
        return devices

    @staticmethod
    def get_device(conn: sqlite3.Connection, device_id: str) -> Optional[DeviceDetail]:
        """Fetch full details for a single device including IP history and recent domains."""
        row = conn.execute(
            """
            SELECT
                d.device_id,
                d.friendly_name,
                d.device_type,
                d.primary_mac,
                d.mac_is_randomized,
                d.vendor,
                d.status,
                d.confidence,
                d.first_seen,
                d.last_seen,
                (
                    SELECT ip_address
                    FROM device_addresses da
                    WHERE da.device_id = d.device_id
                      AND INSTR(da.ip_address, '.') > 0
                    ORDER BY observed_at DESC, id DESC
                    LIMIT 1
                ) AS current_ip,
                (
                    SELECT COUNT(*)
                    FROM dns_queries q
                    WHERE q.device_id = d.device_id
                ) AS query_count,
                (
                    SELECT COUNT(*)
                    FROM dns_queries q
                    WHERE q.device_id = d.device_id AND q.dns_visibility = 'PARTIAL'
                ) AS partial_query_count
            FROM devices d
            WHERE d.device_id = ?
            """,
            (device_id,),
        ).fetchone()

        if not row:
            return None

        # Fetch address history
        addr_rows = conn.execute(
            """
            SELECT id, ip_address, mac_address, hostname, vendor, observed_at
            FROM device_addresses
            WHERE device_id = ?
            ORDER BY observed_at DESC, id DESC
            LIMIT 50
            """,
            (device_id,),
        ).fetchall()
        addresses = [
            DeviceAddressItem(
                id=a["id"],
                ip_address=a["ip_address"],
                mac_address=a["mac_address"],
                hostname=a["hostname"],
                vendor=a["vendor"],
                observed_at=a["observed_at"],
            )
            for a in addr_rows
        ]

        # Fetch status events
        status_rows = conn.execute(
            """
            SELECT id, status, occurred_at
            FROM device_status_events
            WHERE device_id = ?
            ORDER BY occurred_at DESC, id DESC
            LIMIT 20
            """,
            (device_id,),
        ).fetchall()
        status_events = [
            DeviceStatusEventItem(
                id=s["id"],
                status=s["status"],
                occurred_at=s["occurred_at"],
            )
            for s in status_rows
        ]

        # Fetch recent distinct domains
        domain_rows = conn.execute(
            """
            SELECT DISTINCT domain
            FROM dns_queries
            WHERE device_id = ?
            ORDER BY occurred_at DESC
            LIMIT 15
            """,
            (device_id,),
        ).fetchall()
        recent_domains = [d["domain"] for d in domain_rows]

        q_count = row["query_count"] or 0
        p_count = row["partial_query_count"] or 0
        if q_count == 0:
            visibility = "NONE"
        elif p_count > 0:
            visibility = "PARTIAL"
        else:
            visibility = "FULL"

        gateway_ip = _detect_gateway_ip()

        return DeviceDetail(
            device_id=row["device_id"],
            friendly_name=row["friendly_name"],
            device_type=row["device_type"],
            primary_mac=row["primary_mac"],
            mac_is_randomized=bool(row["mac_is_randomized"]),
            vendor=row["vendor"],
            status=_effective_status(row["status"], row["last_seen"]),
            confidence=row["confidence"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            current_ip=row["current_ip"],
            query_count=q_count,
            dns_visibility=visibility,
            is_gateway=bool(gateway_ip and row["current_ip"] == gateway_ip),
            addresses=addresses,
            status_events=status_events,
            recent_domains=recent_domains,
        )

    @staticmethod
    def update_device(
        conn: sqlite3.Connection,
        device_id: str,
        friendly_name: Optional[str] = None,
        device_type: Optional[str] = None,
    ) -> Optional[DeviceDetail]:
        """Update a device's name or type, matching CLI rename and classify behavior."""
        # Check if device exists
        existing = Repository.get_device(conn, device_id)
        if not existing:
            return None

        updates = []
        params = []
        if friendly_name is not None:
            updates.append("friendly_name = ?")
            params.append(friendly_name.strip() if friendly_name else None)
        if device_type is not None:
            updates.append("device_type = ?")
            params.append(device_type.strip() if device_type else None)

        if updates:
            params.append(device_id)
            conn.execute(
                f"UPDATE devices SET {', '.join(updates)} WHERE device_id = ?",
                params,
            )
            conn.commit()

        return Repository.get_device(conn, device_id)

    # ── DNS Activity ──────────────────────────────────────────────────────────

    @staticmethod
    def list_activity(
        conn: sqlite3.Connection,
        device_id: Optional[str] = None,
        domain: Optional[str] = None,
        query_type: Optional[str] = None,
        response_status: Optional[str] = None,
        dns_visibility: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[int, list[DnsQueryItem]]:
        """Fetch paginated DNS query activity log with optional filters."""
        where_clauses: list[str] = []
        params: list = []

        if device_id:
            where_clauses.append("q.device_id = ?")
            params.append(device_id)
        if domain:
            where_clauses.append("q.domain LIKE ?")
            params.append(f"%{domain}%")
        if query_type:
            where_clauses.append("q.query_type = ?")
            params.append(query_type.upper())
        if response_status:
            where_clauses.append("q.response_status = ?")
            params.append(response_status.upper())
        if dns_visibility:
            where_clauses.append("q.dns_visibility = ?")
            params.append(dns_visibility.upper())

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        # Total count query
        count_sql = f"SELECT COUNT(*) FROM dns_queries q {where_sql};"
        total = conn.execute(count_sql, params).fetchone()[0]

        # Paginated items query
        items_sql = f"""
            SELECT
                q.id,
                q.occurred_at,
                q.source_ip,
                q.device_id,
                d.friendly_name AS device_name,
                q.domain,
                q.query_type,
                q.response_status,
                q.resolved_addresses,
                q.dns_visibility
            FROM dns_queries q
            LEFT JOIN devices d ON d.device_id = q.device_id
            {where_sql}
            ORDER BY q.occurred_at DESC, q.id DESC
            LIMIT ? OFFSET ?;
        """
        query_params = params + [max(1, min(limit, 500)), max(0, offset)]
        rows = conn.execute(items_sql, query_params).fetchall()

        items = [
            DnsQueryItem(
                id=r["id"],
                occurred_at=r["occurred_at"],
                source_ip=r["source_ip"],
                device_id=r["device_id"],
                device_name=r["device_name"],
                domain=r["domain"],
                query_type=r["query_type"],
                response_status=r["response_status"],
                resolved_addresses=r["resolved_addresses"],
                dns_visibility=r["dns_visibility"],
            )
            for r in rows
        ]

        return total, items

    # ── Top Domains & Stats ───────────────────────────────────────────────────

    @staticmethod
    def get_top_domains(
        conn: sqlite3.Connection,
        device_id: Optional[str] = None,
        limit: int = 20,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> list[TopDomainItem]:
        """Aggregate most requested domains across the whole network or for a single device."""
        query = """
            SELECT
                domain,
                COUNT(*) AS query_count,
                COUNT(DISTINCT device_id) AS unique_devices
            FROM dns_queries
        """
        params: list = []
        conditions = []
        if device_id:
            conditions.append("device_id = ?")
            params.append(device_id)
        if start_date:
            conditions.append("occurred_at >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("occurred_at <= ?")
            params.append(end_date)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " GROUP BY domain ORDER BY query_count DESC LIMIT ?;"
        params.append(max(1, min(limit, 100)))

        rows = conn.execute(query, params).fetchall()
        return [
            TopDomainItem(
                domain=r["domain"],
                query_count=r["query_count"],
                unique_devices=r["unique_devices"],
            )
            for r in rows
        ]

    @staticmethod
    def get_dns_stats(conn: sqlite3.Connection) -> DnsStatsResponse:
        """Calculate overall DNS observation metrics and visibility health."""
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN dns_visibility = 'FULL' THEN 1 ELSE 0 END) AS full_count,
                SUM(CASE WHEN dns_visibility = 'PARTIAL' THEN 1 ELSE 0 END) AS partial_count,
                COUNT(DISTINCT domain) AS unique_domains,
                COUNT(DISTINCT device_id) AS active_devices
            FROM dns_queries;
            """
        ).fetchone()

        total = row["total"] or 0
        full_count = row["full_count"] or 0
        partial_count = row["partial_count"] or 0
        unique_domains = row["unique_domains"] or 0
        active_devices = row["active_devices"] or 0
        partial_pct = round((partial_count / total * 100.0), 2) if total > 0 else 0.0

        return DnsStatsResponse(
            total_queries=total,
            full_visibility_queries=full_count,
            partial_visibility_queries=partial_count,
            partial_percentage=partial_pct,
            unique_domains=unique_domains,
            active_devices_today=active_devices,
        )

    # ── Health & Diagnostics ──────────────────────────────────────────────────

    @staticmethod
    def check_health(conn: sqlite3.Connection) -> HealthResponse:
        """Check system, database connection, query counts, and background processes."""
        db_path = settings.resolve_database_path()
        db_connected = False
        device_count = 0
        dns_count = 0

        try:
            d_row = conn.execute("SELECT COUNT(*) FROM devices;").fetchone()
            device_count = d_row[0] if d_row else 0
            q_row = conn.execute("SELECT COUNT(*) FROM dns_queries;").fetchone()
            dns_count = q_row[0] if q_row else 0
            db_connected = True
        except Exception:
            db_connected = False

        # Check if dnsmasq is listening on port 53
        dnsmasq_running = False
        try:
            import subprocess
            result = subprocess.run(
                ["ps", "-C", "dnsmasq", "-o", "pid="],
                capture_output=True, text=True, timeout=5,
            )
            dnsmasq_running = bool(result.stdout.strip())
        except Exception:
            dnsmasq_running = False

        # Check ingester state
        ingester_running = False
        pos_file = db_path.parent / ".dns_ingester_pos"
        if pos_file.is_file():
            ingester_running = True

        status = "healthy" if db_connected else "degraded"

        return HealthResponse(
            status=status,
            database_connected=db_connected,
            database_path=str(db_path),
            devices_count=device_count,
            dns_queries_count=dns_count,
            dnsmasq_running=dnsmasq_running,
            ingester_running=ingester_running,
        )
