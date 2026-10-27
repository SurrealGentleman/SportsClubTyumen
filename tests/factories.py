"""Shared test data builders, independent of test modules and HTTP clients.

Database builders commit their records. Scenario-specific builders that only
flush or create custom datasets stay local to the relevant tests.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.privacy import CONSENT_VERSION
from app.core.security import get_password_hash
from app.models import Admin, Competition, RegistrationType


def create_admin(
    db_session: Session,
    *,
    is_active: bool = True,
    password: str = "strong-admin-password",
) -> Admin:
    admin = Admin(
        login="admin",
        password_hash=get_password_hash(password),
        is_active=is_active,
    )
    db_session.add(admin)
    db_session.commit()
    return admin


def create_individual_competition(
    db_session: Session,
    *,
    slug: str = "individual-cup",
    is_registration_open: bool = True,
    deadline: datetime | None = None,
) -> Competition:
    competition = Competition(
        title="Личный турнир",
        slug=slug,
        location="ТюмГУ",
        start_date=date.today() + timedelta(days=20),
        end_date=date.today() + timedelta(days=20),
        registration_deadline=deadline or datetime.now(UTC) + timedelta(days=10),
        registration_type=RegistrationType.individual,
        is_registration_open=is_registration_open,
        is_published=True,
    )
    db_session.add(competition)
    db_session.commit()
    return competition


def create_team_competition(
    db_session: Session,
    *,
    min_team_size: int = 3,
    max_team_size: int = 4,
) -> Competition:
    competition = Competition(
        title="Командный кубок",
        slug="team-cup",
        location="ТюмГУ",
        start_date=date.today() + timedelta(days=20),
        end_date=date.today() + timedelta(days=20),
        registration_deadline=datetime.now(UTC) + timedelta(days=10),
        registration_type=RegistrationType.team,
        min_team_size=min_team_size,
        max_team_size=max_team_size,
        is_registration_open=True,
        is_published=True,
    )
    db_session.add(competition)
    db_session.commit()
    return competition


def valid_payload(email: str = "student@study.utmn.ru") -> dict[str, str]:
    return {
        "full_name": "Иван Иванов",
        "university_email": email,
        "institute": "ИМиКН",
        "course": "2",
        "group_name": "01",
        "phone": "+7 900 000-00-00",
        "personal_data_consent": "on",
        "consent_version": CONSENT_VERSION,
    }


def team_payload(
    member_emails: list[str],
    *,
    captain_email: str = "captain@study.utmn.ru",
    team_name: str = "Ладья",
) -> dict[str, str | list[str]]:
    count = len(member_emails)
    return {
        "team_name": team_name,
        "personal_data_consent": "on",
        "consent_version": CONSENT_VERSION,
        "members_consents_confirmed": "on",
        "captain_name": "Иван Капитанов",
        "captain_email": captain_email,
        "captain_phone": "+7 900 000-00-00",
        "captain_institute": "ИМиКН",
        "captain_course": "3",
        "captain_group_name": "01",
        "member_full_name": [f"Участник {index}" for index in range(1, count + 1)],
        "member_university_email": member_emails,
        "member_institute": ["ИМиКН"] * count,
        "member_course": ["2"] * count,
        "member_group_name": ["02"] * count,
    }
