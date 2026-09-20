"""mitmproxy addon: parental web-observation logger (Phase 19).

Run under mitmdump with ``-s collector/proxy/addon.py``. For every
request/response passing through the explicit proxy it stores ONE metadata
row (never bodies, never Cookie/Authorization headers) plus a search-term
row when the URL is a search submission on a known engine.

Device attribution reuses the discovery store (latest IPv4 → device_id),
so proxy rows join the same devices as DNS rows.

Privacy boundary — hard rules, no exceptions:
  * Cookie, Authorization, Proxy-Authorization, Set-Cookie headers are
    never read into storage (not even their presence is logged).
  * Message bodies are never stored. HTML <title> (200 chars) is the only
    content-derived field, bounded and best-effort.
  * Full URLs ARE stored: they contain the search keywords, which is the
    stated purpose of this addon for parents supervising minor children
    on their own network.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone

from mitmproxy import http

from collector.device_discovery import storage as discovery_storage
from collector.proxy.keywords import extract_search

logger = logging.getLogger(__name__)

DB_PATH = os.environ.get(
    "PROXY_DB_PATH",
    "/opt/parental-safety/collector/data/discovery.sqlite3",
)

# Responses larger than this are streamed (never buffered) — metadata only.
STREAM_ABOVE_BYTES = 1_000_000
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_MAX_TITLE_LEN = 200
_MAX_TEXT_SNIFF = 100_000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_headers(headers: http.Headers) -> dict[str, str | None]:
    """Extract the small set of non-sensitive headers we keep."""
    get = headers.get
    return {
        "user_agent": (get("user-agent") or "")[:512] or None,
        "referer": (get("referer") or "")[:2000] or None,
        "content_type": (get("content-type") or "")[:255] or None,
    }


class ParentalProxy:
    """The addon object mitmproxy loads (looks for module-level `addons`)."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        logger.info("parental-proxy addon ready db=%s", db_path)

    # -- hooks -----------------------------------------------------------

    def responseheaders(self, flow: http.HTTPFlow) -> None:
        """Stream huge bodies instead of buffering them into memory."""
        try:
            length = int(flow.response.headers.get("content-length", "0") or 0)
        except (TypeError, ValueError):
            length = 0
        if length > STREAM_ABOVE_BYTES:
            flow.response.stream = True
            flow.metadata["parental_streamed"] = True

    def response(self, flow: http.HTTPFlow) -> None:
        try:
            self._record(flow)
        except Exception as exc:  # never break the proxy for logging
            logger.warning("parental-proxy record failed error=%s", exc)

    def error(self, flow: http.HTTPFlow) -> None:
        try:
            self._record(flow, failed=True)
        except Exception as exc:
            logger.warning("parental-proxy error-record failed error=%s", exc)

    # -- recording --------------------------------------------------------

    def _client_ip(self, flow: http.HTTPFlow) -> str:
        try:
            address = flow.client_conn.address
            if address:
                return str(address[0])
        except Exception:
            pass
        return "unknown"

    def _page_title(self, flow: http.HTTPFlow) -> str | None:
        if flow.metadata.get("parental_streamed"):
            return None
        try:
            content_type = (flow.response.headers.get("content-type") or "").lower()
        except Exception:
            return None
        if "html" not in content_type:
            return None
        try:
            text = flow.response.content[:_MAX_TEXT_SNIFF].decode("utf-8", errors="replace")
        except Exception:
            return None
        match = _TITLE_RE.search(text)
        if not match:
            return None
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        return title[:_MAX_TITLE_LEN] or None

    def _record(self, flow: http.HTTPFlow, failed: bool = False) -> None:
        request = flow.request
        response = flow.response if not failed else None

        client_ip = self._client_ip(flow)
        occurred_at = _now_iso()
        req_headers = _safe_headers(request.headers)
        try:
            req_size = len(request.content or b"")
        except Exception:
            req_size = 0

        status_code: int | None = None
        resp_content_type: str | None = None
        resp_size = 0
        page_title: str | None = None
        if response is not None:
            status_code = response.status_code
            resp_content_type = (response.headers.get("content-type") or "")[:255] or None
            try:
                resp_size = len(response.content or b"")
            except Exception:
                resp_size = 0
            page_title = self._page_title(flow)

        scheme = request.scheme or "https"
        host = request.host or ""
        try:
            port = int(request.port or (443 if scheme == "https" else 80))
        except (TypeError, ValueError):
            port = 443
        path = request.path or "/"
        full_url = request.url or f"{scheme}://{host}{path}"
        if len(full_url) > 4000:
            full_url = full_url[:4000]

        # Hosts on the ignore list pass through as opaque TCP: mitmproxy
        # never calls HTTP hooks for them, so every row here WAS decrypted.
        intercepted = 1

        with self._lock:
            conn = self._conn
            device_id = discovery_storage.resolve_device_id_for_ip(conn, client_ip)
            conn.execute(
                "INSERT INTO proxy_requests (occurred_at, client_ip, device_id,"
                " method, scheme, host, port, path, full_url, user_agent,"
                " referer, req_content_type, req_size, status_code,"
                " resp_content_type, resp_size, page_title, intercepted)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    occurred_at, client_ip, device_id, request.method.upper(),
                    scheme, host.lower(), port, path[:4000], full_url,
                    req_headers["user_agent"], req_headers["referer"],
                    req_headers["content_type"], req_size, status_code,
                    resp_content_type, resp_size, page_title, intercepted,
                ),
            )
            search = extract_search(host, path)
            if search:
                engine_label, keywords = search
                conn.execute(
                    "INSERT INTO proxy_search_terms (occurred_at, device_id,"
                    " engine, keywords, full_url) VALUES (?, ?, ?, ?, ?)",
                    (occurred_at, device_id, engine_label, keywords, full_url),
                )
                logger.info(
                    "proxy_search device=%s engine=%s keywords=%s",
                    device_id, engine_label, keywords[:80],
                )
            conn.commit()


addons = [ParentalProxy()]
