from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from backend.app.core.auth import (
    session_registry,
    verify_password,
    get_token_from_request,
    get_client_ip,
)
from backend.app.core.config import settings
from backend.app.db.session import get_session
from backend.app.models.audit import AuditLog

router = APIRouter(prefix="/auth", tags=["Security & Authentication"])


class LoginRequest(BaseModel):
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


class LoginResponse(BaseModel):
    authenticated: bool
    token: str
    expires_at: str
    message: str


class ChangePasswordResponse(BaseModel):
    success: bool
    message: str


class AuthStatusResponse(BaseModel):
    authenticated: bool
    auth_enabled: bool
    expires_at: Optional[str] = None


class AuditLogEntry(BaseModel):
    id: int
    timestamp: str
    actor_ip: str
    action: str
    target: Optional[str] = None
    details: Optional[str] = None

    class Config:
        from_attributes = True


@router.post("/login", response_model=LoginResponse)
def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> LoginResponse:
    """Authenticate with parent password and obtain a secure session token."""
    ip = get_client_ip(request)

    if not verify_password(req.password):
        # Record failed attempt in audit log
        audit = AuditLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            actor_ip=ip,
            action="AUTH_LOGIN_FAILED",
            target="parent",
            details=json.dumps({"reason": "Invalid password"}),
        )
        session.add(audit)
        session.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid parent password.",
        )

    # Success: create session token
    token = session_registry.create_session(ip)
    sess_info = session_registry.get_session(token)

    # Set HTTP-only session cookie
    response.set_cookie(
        key="parent_session",
        value=token,
        httponly=True,
        samesite="lax",
        secure=False,  # Set to True if running HTTPS in production
        max_age=settings.SESSION_EXPIRE_HOURS * 3600,
    )

    # Record successful login in audit log
    audit = AuditLog(
        timestamp=datetime.now(timezone.utc).isoformat(),
        actor_ip=ip,
        action="AUTH_LOGIN_SUCCESS",
        target="parent",
        details=json.dumps({"session_expires": sess_info["expires_at"] if sess_info else None}),
    )
    session.add(audit)
    session.commit()

    return LoginResponse(
        authenticated=True,
        token=token,
        expires_at=sess_info["expires_at"] if sess_info else "",
        message="Authentication successful.",
    )


@router.post("/logout")
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
) -> dict:
    """Revoke session token and clear session cookie."""
    token = get_token_from_request(request)
    ip = get_client_ip(request)

    if token:
        session_registry.revoke_token(token)

    response.delete_cookie(key="parent_session")

    audit = AuditLog(
        timestamp=datetime.now(timezone.utc).isoformat(),
        actor_ip=ip,
        action="AUTH_LOGOUT",
        target="parent",
        details=None,
    )
    session.add(audit)
    session.commit()

    return {"authenticated": False, "message": "Logged out successfully."}


@router.get("/status", response_model=AuthStatusResponse)
def auth_status(request: Request) -> AuthStatusResponse:
    """Return current authentication state."""
    token = get_token_from_request(request)
    sess = session_registry.get_session(token)
    is_authed = sess is not None

    return AuthStatusResponse(
        authenticated=is_authed,
        auth_enabled=settings.AUTH_ENABLED,
        expires_at=sess["expires_at"] if sess else None,
    )


@router.post("/change-password", response_model=ChangePasswordResponse)
def change_password(
    req: ChangePasswordRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> ChangePasswordResponse:
    if not verify_password(req.current_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    if len(req.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 6 characters.",
        )
    env_path = Path(__file__).resolve().parents[4] / ".env"
    if not env_path.exists():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=".env file not found.",
        )
    env_text = env_path.read_text()
    lines = env_text.splitlines()
    new_lines = []
    found = False
    for line in lines:
        if line.startswith("PARENT_PASSWORD="):
            new_lines.append(f"PARENT_PASSWORD={req.new_password}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"PARENT_PASSWORD={req.new_password}")
    env_path.write_text("\n".join(new_lines) + "\n")
    settings.PARENT_PASSWORD = req.new_password
    # Invalidate all existing sessions so the old password can't be reused
    # from another browser/tab after the change.
    session_registry.clear()
    audit = AuditLog(
        timestamp=datetime.now(timezone.utc).isoformat(),
        actor_ip=get_client_ip(request),
        action="PASSWORD_CHANGED",
        target="parent",
        details=json.dumps({"method": "api"}),
    )
    session.add(audit)
    session.commit()
    return ChangePasswordResponse(
        success=True,
        message="Password updated successfully. Please log in again with your new password.",
    )


@router.get("/audit", response_model=List[AuditLogEntry])
def get_audit_trail(
    limit: int = 50,
    action: Optional[str] = None,
    session: Session = Depends(get_session),
) -> List[AuditLog]:
    """Inspect recent administrative audit logs."""
    stmt = select(AuditLog).order_by(desc(AuditLog.id)).limit(limit)
    if action:
        stmt = select(AuditLog).where(AuditLog.action == action).order_by(desc(AuditLog.id)).limit(limit)
    return list(session.scalars(stmt).all())
