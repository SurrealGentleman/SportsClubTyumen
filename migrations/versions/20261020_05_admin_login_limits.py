"""Shared admin login rate limits.

Revision ID: 20261020_05
Revises: 20261013_04
"""

from alembic import op
import sqlalchemy as sa

revision = "20261020_05"
down_revision = "20261013_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "admin_login_attempts",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_start", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )
    op.create_index(
        "ix_admin_login_attempts_window_start", "admin_login_attempts", ["window_start"]
    )


def downgrade() -> None:
    op.drop_table("admin_login_attempts")
