from __future__ import annotations

from typing import TYPE_CHECKING
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base

if TYPE_CHECKING:
    from backend.app.models.device import Device


class DnsQuery(Base):
    __tablename__ = "dns_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    device_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    query_type: Mapped[str] = mapped_column(String(16), nullable=False)
    response_status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOERROR")
    resolved_addresses: Mapped[str | None] = mapped_column(Text, nullable=True)
    dns_visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="FULL")

    device: Mapped[Device | None] = relationship("Device", back_populates="dns_queries")

    __table_args__ = (
        Index("idx_dns_device_id", "device_id"),
        Index("idx_dns_occurred_at", "occurred_at"),
        Index("idx_dns_domain", "domain"),
    )

    def __repr__(self) -> str:
        return f"<DnsQuery(id={self.id}, domain={self.domain!r}, device_id={self.device_id!r})>"
