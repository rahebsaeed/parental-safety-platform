"""Phase 2 — DNS log ingester.

Tails the dnsmasq query log file and persists each DNS query to the
SQLite database alongside Phase 1's device data.

Design:
  - Tracks the log file's byte position in a small state file
    (default: next to the database, named `.dns_ingester_pos`) so it can
    resume after a restart without re-processing historical entries.
  - Joins each query's source_ip to a Phase 1 device_id via
    storage.resolve_device_id_for_ip().  Unknown IPs get
    dns_visibility='PARTIAL' — the DoH/DoT bypass signal.
  - Can be run in one-shot mode (process all new lines and exit) or
    continuous tail mode (poll every `poll_interval` seconds).
  - Never crashes on a malformed log line — parse_line() returns None
    for those; see log_parser.py.

Usage (continuous):
    from collector.dns.ingester import Ingester
    ingester = Ingester(log_path="/var/log/parental-safety/dnsmasq.log",
                        db_path="./data/discovery.sqlite3")
    ingester.run_forever()

Usage (one-shot):
    count = ingester.process_new_lines()
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

from collector.device_discovery import storage
from collector.dns.log_parser import LogParser

logger = logging.getLogger(__name__)

_DEFAULT_POLL_INTERVAL = 5  # seconds


class Ingester:
    """Tails a dnsmasq log file and writes DNS query records to SQLite."""

    def __init__(
        self,
        log_path: str | Path,
        db_path: str | Path,
        *,
        pos_file: str | Path | None = None,
        poll_interval: int = _DEFAULT_POLL_INTERVAL,
    ) -> None:
        self.log_path = Path(log_path)
        self.db_path = Path(db_path)
        self.poll_interval = poll_interval

        # Position file: stores the byte offset we've already consumed.
        if pos_file is None:
            self._pos_file = self.db_path.parent / ".dns_ingester_pos"
        else:
            self._pos_file = Path(pos_file)

        self._parser = LogParser()

    # ── position file helpers ─────────────────────────────────────────────────

    def _read_pos(self) -> int:
        """Return the last committed byte offset, or 0 for a fresh start."""
        try:
            return int(self._pos_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            return 0

    def _write_pos(self, pos: int) -> None:
        self._pos_file.write_text(str(pos))

    # ── core processing ───────────────────────────────────────────────────────

    def process_new_lines(self) -> int:
        """Read all new lines since the last committed position, parse them,
        and persist any complete DNS entries to the database.

        Returns the count of entries written.
        """
        if not self.log_path.exists():
            logger.debug("Log file not yet present: %s", self.log_path)
            return 0

        pos = self._read_pos()
        written = 0

        try:
            with self.log_path.open("r", errors="replace") as fh:
                # Handle log rotation: if the file is shorter than our saved
                # position (dnsmasq rotated or truncated the file), reset to 0.
                fh.seek(0, 2)  # seek to end to find size
                file_size = fh.tell()
                if pos > file_size:
                    logger.info(
                        "Log file shrank (%d → %d bytes) — likely rotated, resetting position.",
                        pos,
                        file_size,
                    )
                    pos = 0
                    self._parser = LogParser()  # reset parser state too

                fh.seek(pos)
                conn = storage.init_db(self.db_path)
                try:
                    for raw_line in fh:
                        entry = self._parser.parse_line(raw_line)
                        if entry is not None:
                            written += self._persist(conn, entry)

                    # Flush any buffered incomplete entry (last line in file
                    # may not yet have its reply line — leave it buffered for
                    # the next poll cycle, don't flush here so we don't lose
                    # the reply association).  We only flush on explicit stop.
                    new_pos = fh.tell()
                finally:
                    conn.close()

        except OSError as exc:
            logger.warning("Could not read log file %s: %s", self.log_path, exc)
            return written

        self._write_pos(new_pos)
        if written:
            logger.info("dns_ingester wrote %d new query records", written)
        return written

    def _persist(self, conn: sqlite3.Connection, entry) -> int:  # noqa: ANN001
        """Write one DnsLogEntry to the database. Returns 1 on success."""
        device_id = storage.resolve_device_id_for_ip(conn, entry.source_ip)
        dns_visibility = "FULL" if device_id is not None else "PARTIAL"

        if dns_visibility == "PARTIAL":
            logger.debug(
                "dns_visibility=PARTIAL source_ip=%s domain=%s "
                "(IP not in device_addresses — possible DoH/DoT bypass or new device)",
                entry.source_ip,
                entry.domain,
            )

        storage.insert_dns_query(
            conn,
            occurred_at=entry.occurred_at,
            source_ip=entry.source_ip,
            device_id=device_id,
            domain=entry.domain,
            query_type=entry.query_type,
            response_status=entry.response_status,
            resolved_addresses=entry.resolved_addresses_str,
            dns_visibility=dns_visibility,
        )
        return 1

    def flush_and_stop(self) -> int:
        """Flush the parser's buffered incomplete entry (if any) to disk.
        Call this on clean shutdown so the last query isn't silently dropped.
        """
        final = self._parser.flush()
        if final is None:
            return 0
        conn = storage.init_db(self.db_path)
        try:
            return self._persist(conn, final)
        finally:
            conn.close()

    # ── continuous tail mode ──────────────────────────────────────────────────

    def run_forever(self) -> None:  # pragma: no cover — tested via process_new_lines
        """Poll the log file indefinitely, processing new lines each cycle.
        Blocks until interrupted (SIGINT / SIGTERM).
        """
        logger.info(
            "dns_ingester starting: log=%s db=%s poll_interval=%ds",
            self.log_path,
            self.db_path,
            self.poll_interval,
        )
        try:
            while True:
                self.process_new_lines()
                time.sleep(self.poll_interval)
        except KeyboardInterrupt:
            logger.info("dns_ingester stopping (KeyboardInterrupt)")
        finally:
            flushed = self.flush_and_stop()
            if flushed:
                logger.info("Flushed %d buffered entry/entries on shutdown.", flushed)
