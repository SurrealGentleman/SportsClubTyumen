"""Shared HTTP-level competition lookups and display helpers.

Kept outside individual routers so registrations and competition pages do not
import one another. Business rules remain unchanged during this refactoring.
"""

from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Competition, RegistrationType


def registration_is_open(competition: Competition) -> bool:
    deadline = competition.registration_deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    return (
        competition.is_registration_open
        and datetime.now(UTC) <= deadline
        and (
            competition.registration_type != RegistrationType.team
            or competition.has_valid_team_size
        )
    )


def get_published_competition(db: Session, slug: str) -> Competition:
    competition = db.scalar(
        select(Competition).where(
            Competition.slug == slug,
            Competition.is_published.is_(True),
        )
    )
    if competition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return competition
