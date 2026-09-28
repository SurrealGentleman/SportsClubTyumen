from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.models import Admin, Sport, Training, TrainingGroup


def create_admin(db_session: Session, *, is_active: bool = True) -> Admin:
    admin = Admin(
        login="admin",
        password_hash=get_password_hash("strong-admin-password"),
        is_active=is_active,
    )
    db_session.add(admin)
    db_session.commit()
    return admin


def test_admin_requires_authentication(client: TestClient) -> None:
    response = client.get("/admin/", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["location"].endswith("/admin/login")


def test_admin_rejects_invalid_credentials(
    client: TestClient,
    db_session: Session,
) -> None:
    create_admin(db_session)

    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 400
    assert "Invalid credentials" in response.text


def test_admin_login_opens_crud_sections(
    client: TestClient,
    db_session: Session,
) -> None:
    create_admin(db_session)

    login_response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "strong-admin-password"},
        follow_redirects=False,
    )
    admin_response = client.get("/admin/")

    assert login_response.status_code == 302
    assert admin_response.status_code == 200
    assert "Виды спорта" in admin_response.text
    assert "Тренировки" in admin_response.text
    assert "Соревнования" in admin_response.text
    assert "Заявки" in admin_response.text
    assert "Участники заявок" in admin_response.text
    assert "Панель управления" in admin_response.text
    assert "Быстрые действия" in admin_response.text
    assert "Добавить тренировку" in admin_response.text

    for identity in (
        "sport",
        "training",
        "competition",
        "registration",
        "registration-member",
    ):
        list_response = client.get(f"/admin/{identity}/list")
        create_response = client.get(f"/admin/{identity}/create")

        assert list_response.status_code == 200
        assert create_response.status_code == 200

    assert "Создать" in client.get("/admin/sport/list").text
    assert "Выход" in admin_response.text


def test_admin_forms_use_russian_choices_and_automatic_slug(
    client: TestClient,
    db_session: Session,
) -> None:
    create_admin(db_session)
    client.post(
        "/admin/login",
        data={"username": "admin", "password": "strong-admin-password"},
    )

    sport_form = client.get("/admin/sport/create")
    training_form = client.get("/admin/training/create")
    competition_form = client.get("/admin/competition/create")

    assert 'name="slug"' not in sport_form.text
    assert 'name="image_path"' not in sport_form.text
    assert "Понедельник" in training_form.text
    assert "Воскресенье" in training_form.text
    assert "Мужчины" in training_form.text
    assert "Девушки" in training_form.text
    assert "Общая группа" in training_form.text
    assert "Индивидуальная" in competition_form.text
    assert "Командная" in competition_form.text
    assert "Дата и время Тюмени (UTC+5)" in competition_form.text
    assert 'name="slug"' not in competition_form.text
    assert 'title="Обязательное поле"' in training_form.text
    assert "This is a required field" not in training_form.text

    response = client.post(
        "/admin/sport/create",
        data={
            "name": "Лёгкая атлетика",
            "description": "",
            "is_active": "y",
            "save": "Сохранить",
        },
        follow_redirects=False,
    )
    sport = db_session.query(Sport).filter_by(name="Лёгкая атлетика").one()

    assert response.status_code == 302
    assert sport.slug == "legkaya-atletika"

    training_response = client.post(
        "/admin/training/create",
        data={
            "sport": str(sport.id),
            "group_name": "Общая группа",
            "weekday": "4",
            "start_time": "18:00",
            "end_time": "19:30",
            "location": "Спорткомплекс ТюмГУ",
            "coach_name": "Иван Тренер",
            "coach_email": "",
            "notes": "",
            "is_active": "y",
            "save": "Сохранить",
        },
        follow_redirects=False,
    )
    assert training_response.status_code == 302, training_response.text
    training = db_session.query(Training).one()

    assert training.group_name == TrainingGroup.mixed
    assert training.weekday == 4


def test_inactive_admin_cannot_login(
    client: TestClient,
    db_session: Session,
) -> None:
    create_admin(db_session, is_active=False)

    response = client.post(
        "/admin/login",
        data={"username": "admin", "password": "strong-admin-password"},
    )

    assert response.status_code == 400


def test_admin_logout_clears_session(
    client: TestClient,
    db_session: Session,
) -> None:
    create_admin(db_session)
    client.post(
        "/admin/login",
        data={"username": "admin", "password": "strong-admin-password"},
    )

    logout_response = client.get("/admin/logout", follow_redirects=False)
    admin_response = client.get("/admin/", follow_redirects=False)

    assert logout_response.status_code == 302
    assert logout_response.headers["location"].endswith("/admin/login")
    assert admin_response.status_code == 302
