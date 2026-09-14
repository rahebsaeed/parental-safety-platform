"""Add domain_classifications table.

Revision ID: 0002_domain_classification
Revises: 0001_initial_schema
Create Date: 2026-09-12 23:30:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_domain_classification"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── domain_classifications ────────────────────────────────────────────────
    op.create_table(
        "domain_classifications",
        sa.Column("domain", sa.String(255), primary_key=True),
        sa.Column(
            "category",
            sa.String(64),
            nullable=False,
            server_default="UNCATEGORIZED",
        ),
        sa.Column("rule_type", sa.String(32), nullable=True),
        sa.Column("pattern", sa.String(255), nullable=True),
        sa.Column("is_override", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("classified_at", sa.String(64), nullable=True),
    )
    op.create_index(
        "idx_dc_category", "domain_classifications", ["category"]
    )
    op.create_index(
        "idx_dc_classified_at", "domain_classifications", ["classified_at"]
    )


def downgrade() -> None:
    op.drop_index("idx_dc_classified_at", table_name="domain_classifications")
    op.drop_index("idx_dc_category", table_name="domain_classifications")
    op.drop_table("domain_classifications")
