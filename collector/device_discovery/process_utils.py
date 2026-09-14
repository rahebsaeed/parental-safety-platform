"""Small shared helper for running local read-only diagnostic commands
(`ip`, etc.). Kept separate so network_info.py and arp_scan.py don't each
reimplement subprocess error handling.
"""

from __future__ import annotations

import subprocess


class CommandExecutionError(RuntimeError):
    """A local command failed, wasn't found, or timed out."""


def run_command(args: list[str], timeout: float = 5.0) -> str:
    try:
        result = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError as exc:
        raise CommandExecutionError(
            f"Command not found: {args[0]}. Is iproute2 installed?"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandExecutionError(f"Command timed out: {' '.join(args)}") from exc

    if result.returncode != 0:
        raise CommandExecutionError(
            f"Command failed ({result.returncode}): {' '.join(args)}\n{result.stderr}"
        )
    return result.stdout
