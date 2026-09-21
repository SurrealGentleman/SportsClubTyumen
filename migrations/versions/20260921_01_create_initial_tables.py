"""Create the initial sports club tables.

Revision ID: 20260921_01
Revises:
Create Date: 2026-09-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "admins",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("login", sa.String(length=120), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admins_login", "admins", ["login"], unique=True)

    op.create_table(
        "competitions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.String(length=500), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("registration_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "registration_type",
            sa.Enum("individual", "team", name="registration_type"),
            nullable=False,
        ),
        sa.Column("min_team_size", sa.Integer(), nullable=True),
        sa.Column("max_team_size", sa.Integer(), nullable=True),
        sa.Column("is_registration_open", sa.Boolean(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "end_date >= start_date",
            name="ck_competitions_date_range",
        ),
        sa.CheckConstraint(
            "(registration_type = 'individual' AND min_team_size IS NULL "
            "AND max_team_size IS NULL) OR "
            "(registration_type = 'team' AND min_team_size >= 1 "
            "AND max_team_size >= min_team_size)",
            name="ck_competitions_team_size",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_competitions_slug", "competitions", ["slug"], unique=True)

    op.create_table(
        "sports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_path", sa.String(length=500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_sports_slug", "sports", ["slug"], unique=True)

    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("competition_id", sa.Integer(), nullable=False),
        sa.Column("team_name", sa.String(length=255), nullable=True),
        sa.Column("captain_name", sa.String(length=255), nullable=False),
        sa.Column("captain_email", sa.String(length=320), nullable=False),
        sa.Column("captain_phone", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["competition_id"], ["competitions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_registrations_competition_id",
        "registrations",
        ["competition_id"],
        unique=False,
    )

    op.create_table(
        "trainings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sport_id", sa.Integer(), nullable=False),
        sa.Column("group_name", sa.String(length=120), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("location", sa.String(length=500), nullable=False),
        sa.Column("coach_name", sa.String(length=255), nullable=False),
        sa.Column("coach_email", sa.String(length=320), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_trainings_weekday"),
        sa.ForeignKeyConstraint(["sport_id"], ["sports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trainings_sport_id", "trainings", ["sport_id"], unique=False)

    op.create_table(
        "registration_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("registration_id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("university_email", sa.String(length=320), nullable=False),
        sa.Column("institute", sa.String(length=255), nullable=False),
        sa.Column("course", sa.Integer(), nullable=False),
        sa.Column("group_name", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("is_captain", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["registration_id"], ["registrations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "registration_id",
            "university_email",
            name="uq_registration_members_registration_email",
        ),
    )
    op.create_index(
        "ix_registration_members_registration_id",
        "registration_members",
        ["registration_id"],
        unique=False,
    )
    op.create_index(
        "ix_registration_members_university_email",
        "registration_members",
        ["university_email"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_registration_members_university_email",
        table_name="registration_members",
    )
    op.drop_index(
        "ix_registration_members_registration_id",
        table_name="registration_members",
    )
    op.drop_table("registration_members")
    op.drop_index("ix_trainings_sport_id", table_name="trainings")
    op.drop_table("trainings")
    op.drop_index("ix_registrations_competition_id", table_name="registrations")
    op.drop_table("registrations")
    op.drop_index("ix_sports_slug", table_name="sports")
    op.drop_table("sports")
    op.drop_index("ix_competitions_slug", table_name="competitions")
    op.drop_table("competitions")
    op.drop_index("ix_admins_login", table_name="admins")
    op.drop_table("admins")

    sa.Enum(name="registration_type").drop(op.get_bind(), checkfirst=True)
