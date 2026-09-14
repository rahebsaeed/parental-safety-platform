"""Structured logging setup, matching the spec's compact style:

    INFO  device_discovery device_detected
    WARN  safety_engine    suspicious_domain

Kept as its own module (not inlined in cli.py) so a future systemd-service
entry point (Phase 11) can reuse the same configuration.
"""

from __future__ import annotations

import logging
import sys


class _CompactFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        short_name = record.name.rsplit(".", 1)[-1]
        return f"{record.levelname:<5} {short_name:<18} {record.getMessage()}"


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(_CompactFormatter())

    root = logging.getLogger("collector")
    root.setLevel(level.upper())
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False
