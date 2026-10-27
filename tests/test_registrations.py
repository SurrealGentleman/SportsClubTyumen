from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.privacy import CONSENT_VERSION
from app.models import Competition, Registration, RegistrationMember, RegistrationType


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
