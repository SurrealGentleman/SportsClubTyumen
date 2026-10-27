"""Shared public HTTP request counters.

Revision ID: 20261025_06
Revises: 20261020_05
"""

from alembic import op
import sqlalchemy as sa

revision = "20261025_06"
down_revision = "20261020_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "request_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_request_limits_window_start", "request_limits", ["window_start"]
    )


def downgrade() -> None:
    op.drop_table("request_limits")
