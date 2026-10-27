from datetime import UTC, date, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Competition,
    RegistrationType,
    Sport,
)


def test_slugs_are_generated_and_made_unique(db_session: Session) -> None:
    first_sport = Sport(name="Шахматы")
    second_sport = Sport(name="Шахматы!")
    first_competition = Competition(
        title="Кубок ректора",
        location="ТюмГУ",
        start_date=date(2027, 2, 1),
        end_date=date(2027, 2, 1),
        registration_deadline=datetime(2027, 1, 25, tzinfo=UTC),
        registration_type=RegistrationType.individual,
    )
    second_competition = Competition(
        title="Кубок ректора!",
        location="ТюмГУ",
        start_date=date(2027, 3, 1),
        end_date=date(2027, 3, 1),
        registration_deadline=datetime(2027, 2, 25, tzinfo=UTC),
        registration_type=RegistrationType.individual,
    )
    db_session.add_all(
        [first_sport, second_sport, first_competition, second_competition]
    )
    db_session.commit()

    assert first_sport.slug == "shahmaty"
    assert second_sport.slug == "shahmaty-2"
    assert first_competition.slug == "kubok-rektora"
    assert second_competition.slug == "kubok-rektora-2"


@pytest.mark.parametrize(
    ("minimum", "maximum"), [(None, None), (None, 5), (3, None), (0, 5), (5, 3)]
)
def test_database_rejects_team_competitions_with_invalid_limits(
    db_session: Session, minimum: int | None, maximum: int | None
) -> None:
    competition = Competition(
        title="Командный кубок",
        location="ТюмГУ",
        start_date=date(2027, 2, 1),
        end_date=date(2027, 2, 1),
        registration_deadline=datetime(2027, 1, 25, tzinfo=UTC),
        registration_type=RegistrationType.team,
        min_team_size=minimum,
        max_team_size=maximum,
    )
    db_session.add(competition)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
