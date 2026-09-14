"""Add safety_alerts table.

Revision ID: 0003_safety_alerts
Revises: 0002_domain_classification
Create Date: 2026-09-12 23:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_safety_alerts"
down_revision: Union[str, None] = "0002_domain_classification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── safety_alerts ─────────────────────────────────────────────────────────
    op.create_table(
        "safety_alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("device_id", sa.String(64), sa.ForeignKey("devices.device_id", ondelete="SET NULL"), nullable=True),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("alert_type", sa.String(64), nullable=False),
        sa.Column("severity", sa.String(32), nullable=False, server_default="MEDIUM"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("rule_matched", sa.String(128), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="ACTIVE"),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("dedup_key", sa.String(255), nullable=False),
        sa.Column("created_at", sa.String(64), nullable=False),
        sa.Column("last_seen_at", sa.String(64), nullable=False),
    )
    op.create_index("idx_alerts_device_id", "safety_alerts", ["device_id"])
    op.create_index("idx_alerts_status", "safety_alerts", ["status"])
    op.create_index("idx_alerts_severity", "safety_alerts", ["severity"])
    op.create_index("idx_alerts_dedup_key", "safety_alerts", ["dedup_key"])
    op.create_index("idx_alerts_created_at", "safety_alerts", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_alerts_created_at", table_name="safety_alerts")
    op.drop_index("idx_alerts_dedup_key", table_name="safety_alerts")
    op.drop_index("idx_alerts_severity", table_name="safety_alerts")
    op.drop_index("idx_alerts_status", table_name="safety_alerts")
    op.drop_index("idx_alerts_device_id", table_name="safety_alerts")
    op.drop_table("safety_alerts")
