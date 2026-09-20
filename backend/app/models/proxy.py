"""ORM models for Phase 19 web-proxy observations."""
from __future__ import annotations

from sqlalchemy import Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class ProxyRequest(Base):
    """One HTTP(S) request/response observed by the explicit web proxy.

    Privacy boundary (enforced in the proxy addon, mirrored here by
    absence): Cookie/Authorization headers and message bodies are NEVER
    stored — only metadata, page titles, and search keywords.
    """

    __tablename__ = "proxy_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    client_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    scheme: Mapped[str] = mapped_column(String(16), nullable=False, default="https")
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=443)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_url: Mapped[str] = mapped_column(Text, nullable=False)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    referer: Mapped[str | None] = mapped_column(Text, nullable=True)
    req_content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    req_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resp_content_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resp_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    intercepted: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("idx_proxy_occurred_at", "occurred_at"),
        Index("idx_proxy_device_id", "device_id"),
        Index("idx_proxy_host", "host"),
        Index("idx_proxy_client_ip", "client_ip"),
    )


class ProxySearchTerm(Base):
    """A search query typed on a known engine, extracted from the request URL."""

    __tablename__ = "proxy_search_terms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    device_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    engine: Mapped[str] = mapped_column(String(64), nullable=False)
    keywords: Mapped[str] = mapped_column(String(512), nullable=False)
    full_url: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_psearch_device_id", "device_id"),
        Index("idx_psearch_occurred_at", "occurred_at"),
    )
