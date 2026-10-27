from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import Registration, RegistrationMember
from tests.factories import create_team_competition, team_payload


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
