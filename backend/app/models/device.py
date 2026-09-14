from __future__ import annotations

from typing import TYPE_CHECKING
from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.models.base import Base

if TYPE_CHECKING:
    from backend.app.models.dns import DnsQuery
    from backend.app.models.alert import SafetyAlert


class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    friendly_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    primary_mac: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mac_is_randomized: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="online")
    confidence: Mapped[str] = mapped_column(String(32), nullable=False, default="LOW")
    first_seen: Mapped[str] = mapped_column(String(64), nullable=False)
    last_seen: Mapped[str] = mapped_column(String(64), nullable=False)

    # Relationships
    addresses: Mapped[list[DeviceAddress]] = relationship(
        "DeviceAddress",
        back_populates="device",
        cascade="all, delete-orphan",
        order_by="desc(DeviceAddress.observed_at)",
    )
    status_events: Mapped[list[DeviceStatusEvent]] = relationship(
        "DeviceStatusEvent",
        back_populates="device",
        cascade="all, delete-orphan",
        order_by="desc(DeviceStatusEvent.occurred_at)",
    )
    dns_queries: Mapped[list[DnsQuery]] = relationship(
        "DnsQuery",
        back_populates="device",
    )
    safety_alerts: Mapped[list[SafetyAlert]] = relationship(
        "SafetyAlert",
        back_populates="device",
    )

    def __repr__(self) -> str:
        return f"<Device(id={self.device_id!r}, name={self.friendly_name!r}, status={self.status!r})>"


class DeviceAddress(Base):
    __tablename__ = "device_addresses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ip_address: Mapped[str] = mapped_column(String(64), nullable=False)
    mac_address: Mapped[str | None] = mapped_column(String(32), nullable=True)
    hostname: Mapped[str | None] = mapped_column(String(255), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_at: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    device: Mapped[Device] = relationship("Device", back_populates="addresses")

    __table_args__ = (
        Index("idx_device_addresses_device_id", "device_id"),
        Index("idx_device_addresses_observed_at", "observed_at"),
    )

    def __repr__(self) -> str:
        return f"<DeviceAddress(id={self.id}, device_id={self.device_id!r}, ip={self.ip_address!r})>"


class DeviceStatusEvent(Base):
    __tablename__ = "device_status_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[str] = mapped_column(String(64), nullable=False)

    device: Mapped[Device] = relationship("Device", back_populates="status_events")

    __table_args__ = (
        Index("idx_status_events_device_id", "device_id"),
    )

    def __repr__(self) -> str:
        return f"<DeviceStatusEvent(id={self.id}, device_id={self.device_id!r}, status={self.status!r})>"
