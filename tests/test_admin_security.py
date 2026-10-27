from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.admin.rate_limit import LoginRateLimiter
from app.db.base import Base
from app.models import LoginAttempt, Sport
from tests.admin_helpers import admin_token
from tests.factories import create_admin

PASSWORD = "test-admin-password"


@pytest.fixture()
def authenticated(client: TestClient, db_session: Session) -> TestClient:
    create_admin(db_session, password=PASSWORD)
    response = client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": PASSWORD,
            "csrf_token": admin_token(client),
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    admin_token(client, "/admin/")
    return client


def test_login_requires_csrf_before_checking_password(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def must_not_run(*args):
        pytest.fail("Tokenless request reached password verification")

    monkeypatch.setattr("app.admin.auth.verify_password", must_not_run)
    response = client.post(
        "/admin/login", data={"username": "admin", "password": PASSWORD}
    )
    assert response.status_code == 403


@pytest.mark.parametrize("token", [None, "wrong", "юникод"])
@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/admin/sport/create"),
        ("POST", "/admin/sport/edit/1"),
        ("DELETE", "/admin/sport/delete?pks=1"),
        ("POST", "/admin/sport/import"),
        ("POST", "/admin/logout"),
    ],
)
def test_all_admin_mutations_reject_missing_or_invalid_csrf(
    authenticated: TestClient,
    db_session: Session,
    token: str | None,
    method: str,
    path: str,
) -> None:
    data = {"name": "Injected sport"}
    if token is not None:
        data["csrf_token"] = token
    response = authenticated.request(method, path, data=data, follow_redirects=False)
    assert response.status_code == 403
    assert "Обновите страницу" in response.text
    assert db_session.scalar(select(Sport)) is None
    assert authenticated.get("/admin/", follow_redirects=False).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example"},
        {"Origin": "null"},
        {"Referer": "http://evil.example/admin/"},
        {"Origin": "http://testserver.evil.example"},
        {"Origin": "http://testserver:8080"},
        {"Origin": "http://testserver:bad"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_cross_origin_rejected_even_with_valid_token(
    authenticated: TestClient,
    headers: dict,
) -> None:
    headers = {**headers, "X-CSRF-Token": admin_token(authenticated, "/admin/")}
    response = authenticated.post("/admin/logout", headers=headers)
    assert response.status_code == 403


def test_other_sessions_token_is_rejected(authenticated: TestClient, test_app) -> None:
    with TestClient(test_app) as stranger:
        foreign = admin_token(stranger)
    assert (
        authenticated.post("/admin/logout", data={"csrf_token": foreign}).status_code
        == 403
    )


def test_login_rotates_pre_authentication_token(
    client: TestClient, db_session: Session
):
    create_admin(db_session, password=PASSWORD)
    old = admin_token(client)
    client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": PASSWORD,
            "csrf_token": old,
        },
    )
    new = admin_token(client, "/admin/")
    assert new != old
    assert client.post("/admin/logout", data={"csrf_token": old}).status_code == 403


def test_normal_multipart_create_and_ajax_delete(
    authenticated: TestClient,
    db_session: Session,
) -> None:
    form = authenticated.get("/admin/sport/create")
    token = admin_token(authenticated, "/admin/")
    assert f'name="csrf_token" value="{token}"' in form.text
    assert 'method="post"' in form.text
    assert "admin-csrf.js" in form.text
    assert form.headers["cache-control"] == "no-store"
    created = authenticated.post(
        "/admin/sport/create",
        files={
            "name": (None, "Basketball"),
            "is_active": (None, "y"),
            "csrf_token": (None, token),
            "save": (None, "Сохранить"),
        },
        follow_redirects=False,
    )
    assert created.status_code == 302, created.text
    sport = db_session.scalar(select(Sport))
    assert sport is not None
    response = authenticated.delete(
        f"/admin/sport/delete?pks={sport.id}", headers={"X-CSRF-Token": token}
    )
    assert response.status_code == 200
    db_session.expire_all()
    assert db_session.scalar(select(Sport)) is None


def test_get_logout_does_not_log_out_but_post_does(authenticated: TestClient) -> None:
    token = admin_token(authenticated, "/admin/")
    for method in ("GET", "HEAD"):
        assert (
            authenticated.request(
                method, "/admin/logout", follow_redirects=False
            ).status_code
            == 405
        )
        assert authenticated.get("/admin/", follow_redirects=False).status_code == 200
    response = authenticated.post(
        "/admin/logout",
        data={"csrf_token": token},
        follow_redirects=False,
        headers={"Origin": "http://testserver:80"},
    )
    assert response.status_code == 302
    assert authenticated.get("/admin/", follow_redirects=False).status_code == 302
    assert admin_token(authenticated) != token


def test_large_tokenless_form_is_rejected(authenticated: TestClient) -> None:
    response = authenticated.post(
        "/admin/sport/create",
        content=b"x" * (1024 * 1024 + 1),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 413


def test_login_account_limit_applies_to_new_sessions_and_correct_password(
    client: TestClient,
    test_app,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_admin(db_session, password=PASSWORD)
    calls = []
    monkeypatch.setattr(
        "app.admin.auth.verify_password", lambda *args: calls.append(args) or False
    )
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: 10000)
    for index in range(5):
        with TestClient(test_app, client=(f"192.0.2.{index}", 5000)) as browser:
            token = admin_token(browser)
            response = browser.post(
                "/admin/login",
                data={
                    "username": "admin",
                    "password": "wrong",
                    "csrf_token": token,
                },
            )
            assert response.status_code == 400
    token = admin_token(client)
    response = client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": PASSWORD,
            "csrf_token": token,
        },
    )
    assert response.status_code == 429
    assert response.headers["retry-after"] == "900"
    assert "Слишком много попыток входа" in response.text
    assert len(calls) == 5  # Blocked requests never invoke Argon2.
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: 10900)
    monkeypatch.setattr("app.admin.auth.verify_password", lambda *args: True)
    response = client.post(
        "/admin/login",
        data={
            "username": "admin",
            "password": PASSWORD,
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302


def test_ip_limit_counts_different_unknown_accounts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.admin.auth.verify_password", lambda *args: False)
    token = admin_token(client)
    for index in range(31):
        response = client.post(
            "/admin/login",
            data={
                "username": f"unknown-{index}",
                "password": "wrong",
                "csrf_token": token,
            },
            headers={"X-Forwarded-For": f"192.0.2.{index}"},
        )
        assert response.status_code == (400 if index < 30 else 429)


def test_parallel_workers_share_atomic_counters(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'limits.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine)

    def attempt(index):
        limiter = LoginRateLimiter(
            sessions, "test-secret", account_limit=5, ip_limit=30, window_seconds=900
        )
        return limiter.consume("ADMIN" if index % 2 else "admin", f"192.0.2.{index}")

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(attempt, range(12)))
        assert results.count(0) == 5
        assert sum(value > 0 for value in results) == 7
        with sessions() as session:
            keys = session.scalars(select(LoginAttempt.key)).all()
            assert all(len(key) == 64 and "admin" not in key for key in keys)
    finally:
        engine.dispose()
