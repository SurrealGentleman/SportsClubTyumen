from datetime import UTC, date, datetime, time

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Competition, RegistrationType, Sport, Training


def add_public_content(db_session: Session) -> None:
    basketball = Sport(
        name="Баскетбол",
        slug="basketball",
        description="Студенческие команды ТюмГУ",
    )
    basketball.trainings.extend(
        [
            Training(
                group_name="Девушки",
                weekday=0,
                start_time=time(17, 30),
                end_time=time(19),
                location="ул. Пржевальского, 37",
                coach_name="Владлена Андреевна Гопп",
                coach_email="coach@utmn.ru",
            ),
            Training(
                group_name="Мужчины",
                weekday=2,
                start_time=time(17, 30),
                end_time=time(19),
                location="ул. Республики, 9",
                coach_name="Иван Петров",
                coach_email="petrov@utmn.ru",
            ),
        ]
    )
    inactive_sport = Sport(name="Скрытая секция", slug="hidden", is_active=False)

    published_competition = Competition(
        title="Кубок ректора",
        slug="rectors-cup",
        description="Главный студенческий турнир",
        location="Спортивный комплекс ТюмГУ",
        start_date=date(2027, 2, 1),
        end_date=date(2027, 2, 2),
        registration_deadline=datetime(2027, 1, 25, 18, tzinfo=UTC),
        registration_type=RegistrationType.team,
        min_team_size=5,
        max_team_size=10,
        is_registration_open=True,
        is_published=True,
    )
    hidden_competition = Competition(
        title="Черновик турнира",
        slug="draft-tournament",
        location="ТюмГУ",
        start_date=date(2027, 3, 1),
        end_date=date(2027, 3, 1),
        registration_deadline=datetime(2027, 2, 20, tzinfo=UTC),
        registration_type=RegistrationType.individual,
        is_published=False,
    )

    db_session.add_all(
        [basketball, inactive_sport, published_competition, hidden_competition]
    )
    db_session.commit()


def test_home_page_and_static_assets_are_available(client: TestClient) -> None:
    page_response = client.get("/")
    asset_response = client.get("/static/img/ladya-mark.svg")

    assert page_response.status_code == 200
    assert "ССК «Ладья»" in page_response.text
    assert "Расписание тренировок" in page_response.text
    assert asset_response.status_code == 200
    assert asset_response.headers["content-type"].startswith("image/svg+xml")


def test_schedule_shows_only_active_sports(
    client: TestClient,
    db_session: Session,
) -> None:
    add_public_content(db_session)

    response = client.get("/schedule")

    assert response.status_code == 200
    assert "Баскетбол" in response.text
    assert "/sports/basketball" in response.text
    assert "Скрытая секция" not in response.text


def test_sport_page_reads_training_data_from_database(
    client: TestClient,
    db_session: Session,
) -> None:
    add_public_content(db_session)

    response = client.get("/sports/basketball")
    hidden_response = client.get("/sports/hidden")
    missing_response = client.get("/sports/missing")

    assert response.status_code == 200
    assert "Девушки" in response.text
    assert "Мужчины" in response.text
    assert "17:30–19:00" in response.text
    assert "ул. Пржевальского, 37" in response.text
    assert "ул. Республики, 9" in response.text
    assert "Владлена Андреевна Гопп" in response.text
    assert "Иван Петров" in response.text
    assert hidden_response.status_code == 404
    assert missing_response.status_code == 404


def test_competitions_show_only_published_items(
    client: TestClient,
    db_session: Session,
) -> None:
    add_public_content(db_session)

    list_response = client.get("/competitions")
    detail_response = client.get("/competitions/rectors-cup")
    hidden_response = client.get("/competitions/draft-tournament")

    assert list_response.status_code == 200
    assert "Кубок ректора" in list_response.text
    assert "Черновик турнира" not in list_response.text
    assert detail_response.status_code == 200
    assert "от 5 до 10 участников" in detail_response.text
    assert "Записаться командой" in detail_response.text
    assert "25 января 2027, 23:00 (время Тюмени)" in detail_response.text
    assert "/competitions/rectors-cup/register" in detail_response.text
    assert hidden_response.status_code == 404
