from __future__ import annotations

import secrets
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional

from fastapi import Depends, HTTPException, Request, status

from backend.app.core.config import settings


class SessionRegistry:
    """In-memory registry of active parent session tokens."""

    def __init__(self) -> None:
        self._sessions: Dict[str, dict] = {}

    def create_session(self, actor_ip: str) -> str:
        token = secrets.token_urlsafe(32)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(hours=settings.SESSION_EXPIRE_HOURS)
        self._sessions[token] = {
            "token": token,
            "actor_ip": actor_ip,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "expires_at_dt": expires_at,
        }
        return token

    def validate_token(self, token: str | None) -> bool:
        if not token:
            return False
        session = self._sessions.get(token)
        if not session:
            return False
        if datetime.now(timezone.utc) > session["expires_at_dt"]:
            self._sessions.pop(token, None)
            return False
        return True

    def get_session(self, token: str | None) -> dict | None:
        if not self.validate_token(token):
            return None
        return self._sessions.get(token)

    def revoke_token(self, token: str) -> bool:
        if token in self._sessions:
            del self._sessions[token]
            return True
        return False

    def clear(self) -> None:
        self._sessions.clear()


session_registry = SessionRegistry()


def verify_password(plain_password: str) -> bool:
    """Constant-time comparison against configured PARENT_PASSWORD."""
    return secrets.compare_digest(plain_password, settings.PARENT_PASSWORD)


def get_token_from_request(request: Request) -> Optional[str]:
    """Extract token from Authorization Bearer header or parent_session cookie."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return request.cookies.get("parent_session")


def get_client_ip(request: Request) -> str:
    """Extract client IP address, handling reverse proxy headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


def get_current_parent_optional(request: Request) -> bool:
    """Check if the current request is authenticated without raising an exception."""
    token = get_token_from_request(request)
    return session_registry.validate_token(token)


def require_parent_auth(request: Request) -> bool:
    """Enforce authentication for modifying/administrative actions."""
    if not settings.AUTH_ENABLED:
        return True

    token = get_token_from_request(request)
    if not session_registry.validate_token(token):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Parent authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True
