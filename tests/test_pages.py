from datetime import UTC, date, datetime, time
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.branding import BRAND_ASSETS
from app.models import Competition, RegistrationType, Sport, Training


class BrandMarkup(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: dict[str, str | None] = {}
        self.favicons: list[str | None] = []
        self.body_style = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "img":
            self.images[attributes.get("class") or ""] = attributes.get("src")
        elif tag == "link" and attributes.get("rel") == "icon":
            self.favicons.append(attributes.get("href"))
        elif tag == "body":
            self.body_style = attributes.get("style") or ""


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

    assert page_response.status_code == 200
    assert "ССК «Ладья»" in page_response.text
    assert "Расписание тренировок" in page_response.text


@pytest.mark.parametrize("asset_path", sorted(set(BRAND_ASSETS.values())))
def test_brand_assets_are_available(client: TestClient, asset_path: str) -> None:
    response = client.get(f"/static/{asset_path}")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/png")
    assert response.content.startswith(b"\x89PNG\r\n\x1a\n")


@pytest.mark.parametrize("page_path", ["/", "/schedule", "/competitions"])
@pytest.mark.parametrize("custom_assets", [False, True])
def test_pages_use_brand_assets_for_each_image_role(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    page_path: str,
    custom_assets: bool,
) -> None:
    if custom_assets:
        overrides = {
            "header_logo": "img/logo_utmn_mini2_rus.png",
            "home_logo": "img/logo_utmn_mini1_rus.png",
            "favicon": "img/logo_ladya_no-back_44x32.png",
            "favicon_small": "img/logo_ladya_no-back_22x16.png",
            "background_logo": "img/logo_ladya_white-back_249x180.png",
        }
        for role, asset_path in overrides.items():
            monkeypatch.setitem(BRAND_ASSETS, role, asset_path)

    response = client.get(page_path)
    assert response.status_code == 200
    markup = BrandMarkup()
    markup.feed(response.text)

    expected_urls = {
        role: str(client.app.url_path_for("static", path=asset_path))
        for role, asset_path in BRAND_ASSETS.items()
    }
    assert markup.images["navbar-brand-logo"] == str(
        response.url.copy_with(path=expected_urls["header_logo"])
    )
    assert markup.favicons == [
        str(response.url.copy_with(path=expected_urls["favicon"])),
        str(response.url.copy_with(path=expected_urls["favicon_small"])),
    ]
    background_url = str(response.url.copy_with(path=expected_urls["background_logo"]))
    assert f"--brand-background-image: url('{background_url}')" in markup.body_style
    if page_path == "/":
        assert markup.images["hero-mark"] == str(
            response.url.copy_with(path=expected_urls["home_logo"])
        )


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
    assert "25 января 2027, 23:00" in detail_response.text
    assert "/competitions/rectors-cup/register" in detail_response.text
    assert hidden_response.status_code == 404
