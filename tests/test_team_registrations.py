from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.privacy import CONSENT_VERSION
from app.models import Competition, Registration, RegistrationMember, RegistrationType


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


def test_team_registration_saves_captain_and_members(
    client: TestClient,
    db_session: Session,
) -> None:
    create_team_competition(db_session)

    form_response = client.get("/competitions/team-cup/register")
    response = client.post(
        "/competitions/team-cup/register",
        data=team_payload(
            ["member1@study.utmn.ru", "member2@study.utmn.ru"],
        ),
    )

    registration = db_session.scalar(select(Registration))
    members = list(
        db_session.scalars(select(RegistrationMember).order_by(RegistrationMember.id))
    )

    assert form_response.status_code == 200
    assert "team-registration.js" in form_response.text
    assert "от 3 до 4 участников" in form_response.text
    assert response.status_code == 201
    assert registration is not None
    assert registration.team_name == "Ладья"
    assert len(members) == 3
    assert sum(member.is_captain for member in members) == 1


def test_team_registration_rejects_invalid_member_email_domain(
    client: TestClient,
    db_session: Session,
) -> None:
    create_team_competition(db_session)

    response = client.post(
        "/competitions/team-cup/register",
        data=team_payload(["member@example.com", "member2@study.utmn.ru"]),
    )

    assert response.status_code == 422
    assert "Используйте университетскую почту" in response.text


def test_team_registration_rejects_duplicate_email_inside_team(
    client: TestClient,
    db_session: Session,
) -> None:
    create_team_competition(db_session)

    response = client.post(
        "/competitions/team-cup/register",
        data=team_payload(
            ["captain@study.utmn.ru", "member2@study.utmn.ru"],
        ),
    )

    assert response.status_code == 422
    assert "не должны повторяться" in response.text


def test_team_registration_rejects_too_small_team(
    client: TestClient,
    db_session: Session,
) -> None:
    create_team_competition(db_session, min_team_size=3, max_team_size=5)

    response = client.post(
        "/competitions/team-cup/register",
        data=team_payload(["member1@study.utmn.ru"]),
    )

    assert response.status_code == 409
    assert "не менее 3 участников" in response.text


def test_team_registration_rejects_too_large_team(
    client: TestClient,
    db_session: Session,
) -> None:
    create_team_competition(db_session, min_team_size=2, max_team_size=3)

    response = client.post(
        "/competitions/team-cup/register",
        data=team_payload(
            [
                "member1@study.utmn.ru",
                "member2@study.utmn.ru",
                "member3@study.utmn.ru",
            ]
        ),
    )

    assert response.status_code == 409
    assert "не более 3 участников" in response.text


def test_team_registration_rejects_member_registered_in_another_team(
    client: TestClient,
    db_session: Session,
) -> None:
    create_team_competition(db_session)
    first_response = client.post(
        "/competitions/team-cup/register",
        data=team_payload(
            ["shared@study.utmn.ru", "first@study.utmn.ru"],
            team_name="Первая команда",
        ),
    )

    second_response = client.post(
        "/competitions/team-cup/register",
        data=team_payload(
            ["shared@study.utmn.ru", "second@study.utmn.ru"],
            captain_email="other-captain@study.utmn.ru",
            team_name="Вторая команда",
        ),
    )

    registration_count = db_session.scalar(
        select(func.count()).select_from(Registration)
    )
    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert "уже зарегистрированы" in second_response.text
    assert registration_count == 1


def test_team_name_must_be_unique_within_competition(
    client: TestClient,
    db_session: Session,
) -> None:
    create_team_competition(db_session)
    first_response = client.post(
        "/competitions/team-cup/register",
        data=team_payload(
            ["first1@study.utmn.ru", "first2@study.utmn.ru"],
            team_name="Ладья",
        ),
    )
    second_response = client.post(
        "/competitions/team-cup/register",
        data=team_payload(
            ["second1@study.utmn.ru", "second2@study.utmn.ru"],
            captain_email="other-captain@study.utmn.ru",
            team_name="лАдЬя",
        ),
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert "Команда с таким названием уже зарегистрирована" in second_response.text


def test_legacy_competition_without_limits_shows_configuration_message(
    client: TestClient, db_session: Session
) -> None:
    competition = create_team_competition(db_session)
    # Simulate a legacy row which passed the former CHECK constraint.
    db_session.execute(text("PRAGMA ignore_check_constraints = ON"))
    db_session.execute(
        text(
            "UPDATE competitions SET min_team_size = NULL, max_team_size = NULL WHERE id = :id"
        ),
        {"id": competition.id},
    )
    db_session.commit()
    db_session.execute(text("PRAGMA ignore_check_constraints = OFF"))
    db_session.expire_all()

    detail_response = client.get("/competitions/team-cup")
    form_response = client.get("/competitions/team-cup/register")
    submit_response = client.post(
        "/competitions/team-cup/register",
        data=team_payload(["member1@study.utmn.ru", "member2@study.utmn.ru"]),
    )

    assert detail_response.status_code == 200
    assert "Уточняется организатором" in detail_response.text
    assert "None" not in detail_response.text
    assert form_response.status_code == 409
    assert "допустимый размер команды" in form_response.text
    assert "None" not in form_response.text
    assert 'name="team_name"' not in form_response.text
    assert submit_response.status_code == 409
    assert "допустимый размер команды" in submit_response.text
    assert "не более 1" not in submit_response.text
    assert db_session.scalar(select(func.count()).select_from(Registration)) == 0
