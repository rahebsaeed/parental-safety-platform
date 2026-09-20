"""Add proxy_requests and proxy_search_terms tables (Phase 19: web proxy).

Revision ID: 0005_proxy_observations
Revises: 0004_audit_logs
Create Date: 2026-09-19 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_proxy_observations"
down_revision: Union[str, None] = "0004_audit_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "proxy_requests",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.String(64), nullable=False),
        sa.Column("client_ip", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("method", sa.String(16), nullable=False),
        sa.Column("scheme", sa.String(16), nullable=False, default="https"),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, default=443),
        sa.Column("path", sa.Text(), nullable=False, default="/"),
        sa.Column("full_url", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("referer", sa.Text(), nullable=True),
        sa.Column("req_content_type", sa.String(255), nullable=True),
        sa.Column("req_size", sa.Integer(), nullable=False, default=0),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("resp_content_type", sa.String(255), nullable=True),
        sa.Column("resp_size", sa.Integer(), nullable=False, default=0),
        sa.Column("page_title", sa.String(512), nullable=True),
        sa.Column("intercepted", sa.Integer(), nullable=False, default=1),
    )
    op.create_index("idx_proxy_occurred_at", "proxy_requests", ["occurred_at"])
    op.create_index("idx_proxy_device_id", "proxy_requests", ["device_id"])
    op.create_index("idx_proxy_host", "proxy_requests", ["host"])
    op.create_index("idx_proxy_client_ip", "proxy_requests", ["client_ip"])

    op.create_table(
        "proxy_search_terms",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("occurred_at", sa.String(64), nullable=False),
        sa.Column("device_id", sa.String(64), nullable=True),
        sa.Column("engine", sa.String(64), nullable=False),
        sa.Column("keywords", sa.String(512), nullable=False),
        sa.Column("full_url", sa.Text(), nullable=False),
    )
    op.create_index("idx_psearch_device_id", "proxy_search_terms", ["device_id"])
    op.create_index(
        "idx_psearch_occurred_at", "proxy_search_terms", ["occurred_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_psearch_occurred_at", table_name="proxy_search_terms")
    op.drop_index("idx_psearch_device_id", table_name="proxy_search_terms")
    op.drop_table("proxy_search_terms")
    op.drop_index("idx_proxy_client_ip", table_name="proxy_requests")
    op.drop_index("idx_proxy_host", table_name="proxy_requests")
    op.drop_index("idx_proxy_device_id", table_name="proxy_requests")
    op.drop_index("idx_proxy_occurred_at", table_name="proxy_requests")
    op.drop_table("proxy_requests")
