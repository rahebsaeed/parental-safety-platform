from __future__ import annotations

import json
import time
import logging
from collections import defaultdict
from typing import Callable, Dict, List
from urllib.parse import urlparse

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from backend.app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Sliding-window in-memory rate limiter per client IP."""

    def __init__(self) -> None:
        # ip -> list of timestamps
        self._history: Dict[str, List[float]] = defaultdict(list)
        # Separate strict history for login
        self._login_history: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, ip: str, path: str) -> bool:
        if not settings.RATE_LIMIT_ENABLED:
            return True

        now = time.time()
        window = 60.0  # 1-minute window

        if path.endswith("/auth/login"):
            # Strict limit: 5 requests per minute
            timestamps = self._login_history[ip]
            self._login_history[ip] = [t for t in timestamps if now - t < window]
            if len(self._login_history[ip]) >= 5:
                return False
            self._login_history[ip].append(now)
            return True

        # General API limit: 120 requests per minute
        timestamps = self._history[ip]
        self._history[ip] = [t for t in timestamps if now - t < window]
        if len(self._history[ip]) >= 120:
            return False
        self._history[ip].append(now)
        return True

    def clear(self) -> None:
        self._history.clear()
        self._login_history.clear()


rate_limiter = RateLimiter()


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Applies defense-in-depth security controls:
    1. Sliding-window IP rate limiting
    2. Secure HTTP headers (X-Content-Type-Options, X-Frame-Options, etc.)
    3. CSRF Origin validation for mutating requests
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "127.0.0.1"
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()

        # 1. Rate Limiting Check
        if request.url.path.startswith("/api/"):
            if not rate_limiter.is_allowed(client_ip, request.url.path):
                logger.warning(f"Rate limit exceeded for IP: {client_ip} on {request.url.path}")
                return Response(
                    content=json.dumps(
                        {
                            "detail": "Rate limit exceeded. Please wait before retrying.",
                            "retry_after_seconds": 60,
                        }
                    ),
                    status_code=429,
                    media_type="application/json",
                    headers={"Retry-After": "60"},
                )

        # 2. CSRF / Origin Verification for mutating state
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            origin = request.headers.get("Origin")
            referer = request.headers.get("Referer")
            target = origin or referer
            if target:
                try:
                    parsed = urlparse(target)
                    hostname = parsed.hostname or ""
                    # Allow localhost, 127.0.0.1, and local RFC1918 addresses
                    allowed = (
                        hostname in ("localhost", "127.0.0.1", "0.0.0.0")
                        or hostname.startswith("192.168.")
                        or hostname.startswith("10.")
                        or hostname.startswith("172.16.")
                    )
                    if not allowed:
                        origin_base = f"{parsed.scheme}://{parsed.netloc}"
                        if origin_base not in settings.CORS_ORIGINS:
                            logger.warning(f"CSRF origin validation failed for: {target}")
                            return Response(
                                content=json.dumps({"detail": "Cross-origin state mutation rejected."}),
                                status_code=403,
                                media_type="application/json",
                            )
                except Exception:
                    pass

        # Process request
        response: Response = await call_next(request)

        # 3. Security Headers Injection
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"

        return response
