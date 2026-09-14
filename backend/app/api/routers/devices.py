from __future__ import annotations

import json
import os
import subprocess
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from backend.app.db.session import get_db
from backend.app.db.repository import Repository
from backend.app.schemas.devices import DeviceSummary, DeviceDetail, DeviceUpdate
from backend.app.core.auth import get_client_ip

router = APIRouter(prefix="/devices", tags=["Devices"])


@router.get(
    "",
    response_model=list[DeviceSummary],
    summary="List Discovered Devices",
    description="Retrieve all network devices with current IP, MAC, query volume, and DNS visibility status.",
)
def list_devices(
    status: Optional[str] = Query(None, description="Filter by device status: online or offline"),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[DeviceSummary]:
    return Repository.list_devices(conn, status_filter=status)


@router.post(
    "/scan",
    response_model=dict,
    summary="Run Device Discovery Scan",
    description="Trigger a fresh ARP discovery pass so new devices, IP changes, and online/offline transitions show up immediately instead of waiting for the next scheduled scan.",
)
def trigger_scan(request: Request) -> dict:
    """Trigger a fresh device discovery scan via the collector's Python."""
    python = "/opt/parental-safety/collector/.venv/bin/python"
    env = os.environ.copy()
    env.setdefault("DISCOVERY_DB_PATH", "/opt/parental-safety/collector/data/discovery.sqlite3")
    try:
        proc = subprocess.run(
            [python, "-m", "collector.device_discovery.cli", "scan"],
            capture_output=True, text=True, timeout=120,
            env=env, cwd="/opt/parental-safety",
        )
        output = proc.stdout[-2000:] if proc.stdout else ""
        stderr = proc.stderr[-1000:] if proc.stderr else ""
    except subprocess.TimeoutExpired:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Discovery scan timed out.",
        )
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Discovery CLI not found. Is the collector installed?",
        )

    return {
        "success": proc.returncode == 0,
        "returncode": proc.returncode,
        "message": "Discovery scan completed." if proc.returncode == 0 else "Discovery scan had errors.",
        "output": output.strip()[-500:] if output else "",
        "stderr": stderr.strip()[-500:] if stderr else "",
    }


@router.get(
    "/{device_id}",
    response_model=DeviceDetail,
    summary="Get Device Details",
    description="Fetch a device's detailed address history, status transitions, and recent domains queried.",
)
def get_device(
    device_id: str,
    conn: sqlite3.Connection = Depends(get_db),
) -> DeviceDetail:
    device = Repository.get_device(conn, device_id)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found",
        )
    return device


@router.patch(
    "/{device_id}",
    response_model=DeviceDetail,
    summary="Update Device Label or Type",
    description="Rename a device with a friendly name or update its classification (matching CLI rename/classify).",
)
def update_device(
    device_id: str,
    payload: DeviceUpdate,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db),
) -> DeviceDetail:
    updated = Repository.update_device(
        conn,
        device_id=device_id,
        friendly_name=payload.friendly_name,
        device_type=payload.device_type,
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found",
        )

    # Record administrative action in audit log
    try:
        conn.execute(
            "INSERT INTO audit_logs (timestamp, actor_ip, action, target, details) VALUES (?, ?, ?, ?, ?)",
            (
                datetime.now(timezone.utc).isoformat(),
                get_client_ip(request),
                "DEVICE_UPDATE",
                device_id,
                json.dumps(payload.model_dump(exclude_unset=True)),
            ),
        )
        conn.commit()
    except Exception:
        pass

    return updated
