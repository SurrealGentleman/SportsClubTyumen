"""SQL in async workflows must stay in workers with short-lived sessions."""

import asyncio
from contextlib import contextmanager
from threading import get_ident

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.dependencies import get_session_factory
from app.models import Competition, Registration
from app.main import create_app
from tests.admin_helpers import admin_login
from tests.test_admin import create_admin
from tests.test_registrations import create_individual_competition, valid_payload
from tests.test_team_registrations import create_team_competition, team_payload


def assert_no_event_loop():
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    pytest.fail("Synchronous database work reached the event-loop thread")


@contextmanager
def worker_sql_only(engine):
    statements = []

    def check_thread(conn, cursor, statement, parameters, context, many):
        assert_no_event_loop()
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", check_thread)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", check_thread)


@pytest.mark.parametrize("team", [False, True])
def test_registration_sql_runs_outside_event_loop(client, db_session, db_engine, team):
    if team:
        create_team_competition(db_session)
        path = "/competitions/team-cup/register"
        payload = team_payload(["first@study.utmn.ru", "second@study.utmn.ru"])
    else:
        create_individual_competition(db_session)
        path, payload = "/competitions/individual-cup/register", valid_payload()
    with worker_sql_only(db_engine) as statements:
        response = client.post(path, data=payload)
    assert response.status_code == 201
    assert any("INSERT INTO registrations" in sql for sql in statements)


def test_public_get_uses_the_app_session_factory(
    db_engine,
    db_session,
    testing_session_maker,
):
    competition = create_individual_competition(db_session)
    app = create_app(db_engine=db_engine, session_maker=testing_session_maker)
    assert not app.dependency_overrides
    with TestClient(app) as client:
        response = client.get(f"/competitions/{competition.slug}")
    assert response.status_code == 200
    assert competition.title in response.text


def test_admin_login_dashboard_and_export_sql_run_in_workers(
    client, db_session, db_engine
):
    create_admin(db_session)
    competition = create_individual_competition(db_session)
    with worker_sql_only(db_engine) as statements:
        response = admin_login(
            client,
            data={
                "username": "admin",
                "password": "strong-admin-password",
            },
        )
        assert response.status_code == 200
        assert "Панель управления" in response.text
        exported = client.get(
            f"/admin/competition/action/export-xlsx?pks={competition.id}"
        )
    assert exported.status_code == 200
    assert exported.content.startswith(b"PK")
    assert any("admins" in sql for sql in statements)
    assert any("count(" in sql.lower() for sql in statements)


def test_captcha_does_not_hold_a_database_connection(
    client,
    db_session,
    db_engine,
    monkeypatch,
):
    create_individual_competition(db_session)
    active = set()
    checked = []

    def checkout(connection, record, proxy):
        active.add(id(connection))

    def checkin(connection, record):
        active.discard(id(connection))

    def verify(token, host):
        assert_no_event_loop()
        assert not active, "A database connection was held during CAPTCHA verification"
        checked.append(True)

    event.listen(db_engine, "checkout", checkout)
    event.listen(db_engine, "checkin", checkin)
    monkeypatch.setattr("app.routers.registrations.verify_smartcaptcha", verify)
    try:
        response = client.post(
            "/competitions/individual-cup/register", data=valid_payload()
        )
    finally:
        event.remove(db_engine, "checkout", checkout)
        event.remove(db_engine, "checkin", checkin)
    assert response.status_code == 201
    assert checked == [True]
    assert not active


def test_registration_rechecks_settings_after_captcha(
    client,
    db_session,
    testing_session_maker,
    monkeypatch,
):
    competition = create_individual_competition(db_session)

    def close_registration(token, host):
        with testing_session_maker.begin() as session:
            session.get(Competition, competition.id).is_registration_open = False

    monkeypatch.setattr(
        "app.routers.registrations.verify_smartcaptcha", close_registration
    )
    response = client.post(
        "/competitions/individual-cup/register", data=valid_payload()
    )
    assert response.status_code == 409
    assert "Приём заявок на это соревнование закрыт" in response.text
    assert db_session.scalar(select(Registration)) is None


def test_registration_worker_owns_session_lifecycle(test_app, db_engine, db_session):
    create_individual_competition(db_session)
    sessions = []

    class ThreadBoundSession(Session):
        def __init__(self, *args, **kwargs):
            assert_no_event_loop()
            super().__init__(*args, **kwargs)
            self.owner_thread = get_ident()
            self.was_closed = False
            sessions.append(self)

        def _execute_internal(self, *args, **kwargs):
            assert_no_event_loop()
            assert get_ident() == self.owner_thread
            return super()._execute_internal(*args, **kwargs)

        def close(self):
            assert_no_event_loop()
            assert get_ident() == self.owner_thread
            self.was_closed = True
            return super().close()

    factory = sessionmaker(db_engine, class_=ThreadBoundSession, expire_on_commit=False)
    test_app.dependency_overrides[get_session_factory] = lambda: factory
    try:
        with TestClient(test_app) as client:
            response = client.post(
                "/competitions/individual-cup/register", data=valid_payload()
            )
    finally:
        test_app.dependency_overrides.pop(get_session_factory)
    assert response.status_code == 201
    assert len(sessions) == 2
    assert all(session.was_closed for session in sessions)


def test_registration_worker_closes_and_rolls_back_on_error(
    test_app,
    db_session,
    testing_session_maker,
    monkeypatch,
):
    create_individual_competition(db_session)
    seen = []

    def fail(db, *, competition, registration_in):
        seen.append(db)
        db.add(
            Registration(
                competition=competition,
                captain_name="Test",
                captain_email="test@study.utmn.ru",
                captain_phone="123",
            )
        )
        db.flush()
        raise RuntimeError("Simulated storage error")

    monkeypatch.setattr(
        "app.services.registrations.create_individual_registration", fail
    )
    with TestClient(test_app, raise_server_exceptions=False) as client:
        response = client.post(
            "/competitions/individual-cup/register", data=valid_payload()
        )
    assert response.status_code == 500
    assert seen and not seen[0].in_transaction()
    with testing_session_maker() as session:
        assert session.scalar(select(Registration)) is None
