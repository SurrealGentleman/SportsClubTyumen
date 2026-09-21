from datetime import UTC, date, datetime, time

from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (
    Admin,
    Competition,
    Registration,
    RegistrationMember,
    RegistrationType,
    Sport,
    Training,
)


def test_metadata_contains_stage_one_tables() -> None:
    assert set(Base.metadata.tables) == {
        "admins",
        "competitions",
        "registration_members",
        "registrations",
        "sports",
        "trainings",
    }


def test_domain_models_can_be_persisted(db_session: Session) -> None:
    sport = Sport(name="Баскетбол", slug="basketball")
    sport.trainings.append(
        Training(
            group_name="Девушки",
            weekday=0,
            start_time=time(17, 30),
            end_time=time(19),
            location="ул. Пржевальского, 37",
            coach_name="Владлена Андреевна Гопп",
            coach_email="coach@utmn.ru",
        )
    )
    competition = Competition(
        title="Кубок ректора",
        slug="rectors-cup",
        location="ТюмГУ",
        start_date=date(2027, 2, 1),
        end_date=date(2027, 2, 2),
        registration_deadline=datetime(2027, 1, 25, tzinfo=UTC),
        registration_type=RegistrationType.team,
        min_team_size=2,
        max_team_size=5,
        is_published=True,
    )
    registration = Registration(
        team_name="Ладья",
        captain_name="Иван Иванов",
        captain_email="ivanov@utmn.ru",
        captain_phone="+7 900 000-00-00",
    )
    registration.members.append(
        RegistrationMember(
            full_name="Иван Иванов",
            university_email="ivanov@utmn.ru",
            institute="ИМиКН",
            course=2,
            group_name="01",
            phone="+7 900 000-00-00",
            is_captain=True,
        )
    )
    competition.registrations.append(registration)
    admin = Admin(login="admin", password_hash="not-a-plain-text-password")

    db_session.add_all([sport, competition, admin])
    db_session.commit()

    assert sport.id is not None
    assert sport.trainings[0].sport_id == sport.id
    assert competition.registrations[0].members[0].is_captain is True
    assert admin.id is not None
