from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Registration, RegistrationMember
from tests.factories import create_individual_competition, valid_payload


def test_individual_registration_saves_registration_and_member(
    client: TestClient,
    db_session: Session,
) -> None:
    create_individual_competition(db_session)

    form_response = client.get("/competitions/individual-cup/register")
    response = client.post(
        "/competitions/individual-cup/register",
        data=valid_payload("Student@study.utmn.ru"),
    )

    registration = db_session.scalar(select(Registration))
    member = db_session.scalar(select(RegistrationMember))

    assert form_response.status_code == 200
    assert "student@study.utmn.ru" in form_response.text
    assert response.status_code == 201
    assert "Вы зарегистрированы" in response.text
    assert registration is not None
    assert registration.team_name is None
    assert registration.captain_email == "student@study.utmn.ru"
    assert member is not None
    assert member.university_email == "student@study.utmn.ru"
    assert member.is_captain is True


def test_individual_registration_rejects_non_university_email(
    client: TestClient,
    db_session: Session,
) -> None:
    create_individual_competition(db_session)

    response = client.post(
        "/competitions/individual-cup/register",
        data=valid_payload("student@example.com"),
    )

    registration_count = db_session.scalar(
        select(func.count()).select_from(Registration)
    )
    assert response.status_code == 422
    assert "Используйте университетскую почту" in response.text
    assert registration_count == 0


def test_individual_registration_rejects_duplicate_email(
    client: TestClient,
    db_session: Session,
) -> None:
    create_individual_competition(db_session)
    first_response = client.post(
        "/competitions/individual-cup/register",
        data=valid_payload(),
    )

    second_response = client.post(
        "/competitions/individual-cup/register",
        data=valid_payload("STUDENT@study.utmn.ru"),
    )

    registration_count = db_session.scalar(
        select(func.count()).select_from(Registration)
    )
    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert "уже зарегистрирован" in second_response.text
    assert registration_count == 1


def test_individual_registration_rejects_expired_deadline(
    client: TestClient,
    db_session: Session,
) -> None:
    create_individual_competition(
        db_session,
        deadline=datetime.now(UTC) - timedelta(minutes=1),
    )

    response = client.post(
        "/competitions/individual-cup/register",
        data=valid_payload(),
    )

    assert response.status_code == 409
    assert "Срок подачи заявок уже истёк" in response.text


def test_individual_registration_rejects_closed_registration(
    client: TestClient,
    db_session: Session,
) -> None:
    create_individual_competition(db_session, is_registration_open=False)

    response = client.post(
        "/competitions/individual-cup/register",
        data=valid_payload(),
    )

    assert response.status_code == 409
    assert "Приём заявок" in response.text
