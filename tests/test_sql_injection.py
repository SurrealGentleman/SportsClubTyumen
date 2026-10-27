"""Untrusted input stays in SQL parameters and cannot bypass authentication."""

from sqlalchemy import event, select

from app.models import Registration, Sport
from tests.admin_helpers import admin_login
from tests.factories import create_admin, create_individual_competition, valid_payload


def test_sql_injection_cannot_authenticate(client, db_session):
    create_admin(db_session)
    response = admin_login(
        client,
        data={"username": "admin' OR '1'='1' --", "password": "strong-admin-password"},
        follow_redirects=False,
    )
    assert response.status_code == 400
    assert client.get("/admin/", follow_redirects=False).is_redirect


def test_admin_search_uses_bound_parameters(client, db_session, db_engine):
    create_admin(db_session)
    admin_login(client, data={"username": "admin", "password": "strong-admin-password"})
    payload = "Robert'); DROP TABLE sports;--"
    bindings = []

    def capture(conn, cursor, statement, parameters, context, many):
        if payload in str(parameters):
            bindings.append(payload not in statement)

    event.listen(db_engine, "before_cursor_execute", capture)
    try:
        response = client.get("/admin/sport/list", params={"search": payload})
    finally:
        event.remove(db_engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert bindings and all(bindings)
    assert list(db_session.scalars(select(Sport))) == []


def test_registration_treats_sql_payload_as_literal(client, db_session, db_engine):
    create_individual_competition(db_session)
    payload = "Robert'); DROP TABLE registrations;--"
    bindings = []

    def capture(conn, cursor, statement, parameters, context, many):
        if payload in str(parameters):
            bindings.append(payload not in statement)

    event.listen(db_engine, "before_cursor_execute", capture)
    try:
        data = {**valid_payload(), "full_name": payload}
        response = client.post("/competitions/individual-cup/register", data=data)
    finally:
        event.remove(db_engine, "before_cursor_execute", capture)
    assert response.status_code == 201
    assert bindings and all(bindings)
    assert db_session.scalar(select(Registration)).captain_name == payload
