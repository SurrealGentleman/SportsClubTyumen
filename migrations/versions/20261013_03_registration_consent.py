"""Record registration consent without backfilling historical applications.

Revision ID: 20261013_03
Revises: 20260923_02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261013_03"
down_revision: str | None = "20260923_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "registrations",
        sa.Column(
            "personal_data_consent_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.add_column(
        "registrations",
        sa.Column("consent_document_version", sa.String(64), nullable=True),
    )
    op.add_column(
        "registrations", sa.Column("consent_document_text", sa.Text(), nullable=True)
    )
    op.add_column(
        "registrations",
        sa.Column(
            "members_consents_confirmed_at", sa.DateTime(timezone=True), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("registrations", "members_consents_confirmed_at")
    op.drop_column("registrations", "consent_document_text")
    op.drop_column("registrations", "consent_document_version")
    op.drop_column("registrations", "personal_data_consent_at")
