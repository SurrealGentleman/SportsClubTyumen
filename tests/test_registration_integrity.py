"""Registration rechecks, short-lived connections and transaction rollback."""

import asyncio

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, select

from app.models import Competition, Registration
from tests.factories import (
    create_individual_competition,
    valid_payload,
)


def assert_no_event_loop():
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    pytest.fail("Synchronous database work reached the event-loop thread")


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
