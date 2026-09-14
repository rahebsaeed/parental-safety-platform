"""Initial baseline schema: devices, device_addresses, device_status_events, dns_queries

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-09-12 23:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── devices ───────────────────────────────────────────────────────────────
    op.create_table(
        "devices",
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("friendly_name", sa.String(length=100), nullable=True),
        sa.Column("device_type", sa.String(length=50), nullable=True),
        sa.Column("primary_mac", sa.String(length=32), nullable=True),
        sa.Column("mac_is_randomized", sa.Integer(), server_default="0", nullable=False),
        sa.Column("vendor", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="online", nullable=False),
        sa.Column("confidence", sa.String(length=32), server_default="LOW", nullable=False),
        sa.Column("first_seen", sa.String(length=64), nullable=False),
        sa.Column("last_seen", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("device_id"),
    )

    # ── device_addresses ──────────────────────────────────────────────────────
    op.create_table(
        "device_addresses",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=False),
        sa.Column("mac_address", sa.String(length=32), nullable=True),
        sa.Column("hostname", sa.String(length=255), nullable=True),
        sa.Column("vendor", sa.String(length=255), nullable=True),
        sa.Column("observed_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_device_addresses_device_id", "device_addresses", ["device_id"], unique=False)
    op.create_index("idx_device_addresses_observed_at", "device_addresses", ["observed_at"], unique=False)

    # ── device_status_events ──────────────────────────────────────────────────
    op.create_table(
        "device_status_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_status_events_device_id", "device_status_events", ["device_id"], unique=False)

    # ── dns_queries ───────────────────────────────────────────────────────────
    op.create_table(
        "dns_queries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("occurred_at", sa.String(length=64), nullable=False),
        sa.Column("source_ip", sa.String(length=64), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=True),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("query_type", sa.String(length=16), nullable=False),
        sa.Column("response_status", sa.String(length=32), server_default="NOERROR", nullable=False),
        sa.Column("resolved_addresses", sa.Text(), nullable=True),
        sa.Column("dns_visibility", sa.String(length=16), server_default="FULL", nullable=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.device_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_dns_device_id", "dns_queries", ["device_id"], unique=False)
    op.create_index("idx_dns_occurred_at", "dns_queries", ["occurred_at"], unique=False)
    op.create_index("idx_dns_domain", "dns_queries", ["domain"], unique=False)


def downgrade() -> None:
    op.drop_index("idx_dns_domain", table_name="dns_queries")
    op.drop_index("idx_dns_occurred_at", table_name="dns_queries")
    op.drop_index("idx_dns_device_id", table_name="dns_queries")
    op.drop_table("dns_queries")

    op.drop_index("idx_status_events_device_id", table_name="device_status_events")
    op.drop_table("device_status_events")

    op.drop_index("idx_device_addresses_observed_at", table_name="device_addresses")
    op.drop_index("idx_device_addresses_device_id", table_name="device_addresses")
    op.drop_table("device_addresses")

    op.drop_table("devices")
