from __future__ import annotations

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.app.models.base import Base
from backend.app.models.device import Device, DeviceAddress, DeviceStatusEvent
from backend.app.models.dns import DnsQuery


@pytest.fixture
def orm_session(tmp_path) -> Session:  # noqa: ANN001
    db_file = tmp_path / "test_models.sqlite3"
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()


def test_create_device_and_addresses(orm_session: Session) -> None:
    device = Device(
        device_id="dev_100",
        friendly_name="Test Phone",
        device_type="Android",
        primary_mac="00:11:22:33:44:55",
        mac_is_randomized=0,
        vendor="Samsung",
        status="online",
        confidence="HIGH",
        first_seen="2026-09-12 10:00:00",
        last_seen="2026-09-12 12:00:00",
    )
    orm_session.add(device)
    orm_session.commit()

    # Add addresses
    addr1 = DeviceAddress(
        device_id="dev_100",
        ip_address="192.168.1.150",
        mac_address="00:11:22:33:44:55",
        hostname="phone.local",
        observed_at="2026-09-12 10:00:00",
    )
    addr2 = DeviceAddress(
        device_id="dev_100",
        ip_address="192.168.1.151",
        mac_address="00:11:22:33:44:55",
        hostname="phone.local",
        observed_at="2026-09-12 12:00:00",
    )
    orm_session.add_all([addr1, addr2])
    orm_session.commit()

    # Query via relationship
    loaded = orm_session.scalar(select(Device).where(Device.device_id == "dev_100"))
    assert loaded is not None
    assert loaded.friendly_name == "Test Phone"
    assert len(loaded.addresses) == 2
    assert loaded.addresses[0].ip_address == "192.168.1.151"  # ordered by observed_at DESC


def test_device_cascade_delete(orm_session: Session) -> None:
    device = Device(
        device_id="dev_200",
        friendly_name="Temporary Device",
        first_seen="2026-09-12 10:00:00",
        last_seen="2026-09-12 12:00:00",
    )
    addr = DeviceAddress(
        device_id="dev_200",
        ip_address="192.168.1.200",
        observed_at="2026-09-12 10:00:00",
    )
    event = DeviceStatusEvent(
        device_id="dev_200",
        status="online",
        occurred_at="2026-09-12 10:00:00",
    )
    orm_session.add_all([device, addr, event])
    orm_session.commit()

    # Delete device
    orm_session.delete(device)
    orm_session.commit()

    # Verify addresses and status events were cascaded
    addrs = orm_session.scalars(select(DeviceAddress).where(DeviceAddress.device_id == "dev_200")).all()
    events = orm_session.scalars(select(DeviceStatusEvent).where(DeviceStatusEvent.device_id == "dev_200")).all()
    assert len(addrs) == 0
    assert len(events) == 0


def test_dns_query_relationship(orm_session: Session) -> None:
    device = Device(
        device_id="dev_300",
        friendly_name="DNS Client",
        first_seen="2026-09-12 10:00:00",
        last_seen="2026-09-12 12:00:00",
    )
    dns_q = DnsQuery(
        occurred_at="2026-09-12 12:00:01",
        source_ip="192.168.1.160",
        device_id="dev_300",
        domain="wikipedia.org",
        query_type="A",
        response_status="NOERROR",
        resolved_addresses="198.35.26.96",
        dns_visibility="FULL",
    )
    orm_session.add_all([device, dns_q])
    orm_session.commit()

    loaded_q = orm_session.scalar(select(DnsQuery).where(DnsQuery.domain == "wikipedia.org"))
    assert loaded_q is not None
    assert loaded_q.device is not None
    assert loaded_q.device.friendly_name == "DNS Client"
