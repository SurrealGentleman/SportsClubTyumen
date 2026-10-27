"""Require explicit team sizes while preserving legacy competitions.

Revision ID: 20261013_04
Revises: 20261013_03
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261013_04"
down_revision: str | None = "20261013_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_competitions_team_size", "competitions", type_="check")
    # Enforce the rule for new inserts and updates without inventing limits
    # for previously created competitions with missing team sizes.
    op.create_check_constraint(
        "ck_competitions_team_size",
        "competitions",
        "(registration_type = 'individual' AND min_team_size IS NULL AND max_team_size IS NULL) OR "
        "(registration_type = 'team' AND min_team_size IS NOT NULL AND max_team_size IS NOT NULL "
        "AND min_team_size >= 1 AND max_team_size >= min_team_size)",
        postgresql_not_valid=True,
    )


def downgrade() -> None:
    op.drop_constraint("ck_competitions_team_size", "competitions", type_="check")
    op.create_check_constraint(
        "ck_competitions_team_size",
        "competitions",
        "(registration_type = 'individual' AND min_team_size IS NULL AND max_team_size IS NULL) OR "
        "(registration_type = 'team' AND min_team_size >= 1 AND max_team_size >= min_team_size)",
    )
