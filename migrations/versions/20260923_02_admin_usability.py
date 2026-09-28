"""Improve admin data constraints and training groups.

Revision ID: 20260923_02
Revises: 20260921_01
Create Date: 2026-09-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260923_02"
down_revision: str | None = "20260921_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Preserve duplicate teams by numbering later applications before adding
    # the case-insensitive uniqueness rule.
    op.execute(
        sa.text(
            """
            WITH numbered AS (
                SELECT id,
                       row_number() OVER (
                           PARTITION BY competition_id, lower(team_name)
                           ORDER BY id
                       ) AS duplicate_number
                FROM registrations
                WHERE team_name IS NOT NULL
            )
            UPDATE registrations AS registration
            SET team_name = registration.team_name || ' (' ||
                            numbered.duplicate_number || ')'
            FROM numbered
            WHERE registration.id = numbered.id
              AND numbered.duplicate_number > 1
            """
        )
    )
    op.create_index(
        "uq_registrations_competition_team_name_ci",
        "registrations",
        ["competition_id", sa.text("lower(team_name)")],
        unique=True,
        postgresql_where=sa.text("team_name IS NOT NULL"),
    )

    op.execute(
        sa.text(
            """
            UPDATE trainings
            SET group_name = CASE
                WHEN lower(group_name) IN ('мужчины', 'мужская') THEN 'Мужчины'
                WHEN lower(group_name) IN ('женщины', 'девушки', 'женская')
                    THEN 'Девушки'
                ELSE 'Общая группа'
            END
            """
        )
    )
    op.create_check_constraint(
        "training_group",
        "trainings",
        "group_name IN ('Мужчины', 'Девушки', 'Общая группа')",
    )


def downgrade() -> None:
    op.drop_constraint("training_group", "trainings", type_="check")
    op.drop_index(
        "uq_registrations_competition_team_name_ci",
        table_name="registrations",
    )
