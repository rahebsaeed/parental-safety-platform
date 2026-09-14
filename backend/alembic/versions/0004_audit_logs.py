"""Add audit_logs table.

Revision ID: 0004_audit_logs
Revises: 0003_safety_alerts
Create Date: 2026-09-13 01:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_audit_logs"
down_revision: Union[str, None] = "0003_safety_alerts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.String(64), nullable=False),
        sa.Column("actor_ip", sa.String(64), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target", sa.String(255), nullable=True),
        sa.Column("details", sa.Text(), nullable=True),
    )
    op.create_index("idx_audit_timestamp", "audit_logs", ["timestamp"])
    op.create_index("idx_audit_action", "audit_logs", ["action"])
    op.create_index("idx_audit_action_timestamp", "audit_logs", ["action", "timestamp"])


def downgrade() -> None:
    op.drop_index("idx_audit_action_timestamp", table_name="audit_logs")
    op.drop_index("idx_audit_action", table_name="audit_logs")
    op.drop_index("idx_audit_timestamp", table_name="audit_logs")
    op.drop_table("audit_logs")
