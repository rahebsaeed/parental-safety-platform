"""ORM model for Phase 6 Safety Alerts."""
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


class SafetyAlert(Base):
    """Stores generated safety alerts with explainability and deduplication counters."""

    __tablename__ = "safety_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="MEDIUM", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rule_matched: Mapped[str] = mapped_column(String(128), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    dedup_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    last_seen_at: Mapped[str] = mapped_column(String(64), nullable=False)

    device: Mapped[Device | None] = relationship("Device", back_populates="safety_alerts")

    __table_args__ = (
        Index("idx_alerts_device_id", "device_id"),
        Index("idx_alerts_status", "status"),
        Index("idx_alerts_severity", "severity"),
        Index("idx_alerts_dedup_key", "dedup_key"),
        Index("idx_alerts_created_at", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<SafetyAlert(id={self.id}, type={self.alert_type!r}, "
            f"severity={self.severity!r}, domain={self.domain!r}, count={self.occurrence_count})>"
        )
