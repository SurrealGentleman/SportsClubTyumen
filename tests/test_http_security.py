import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app.admin.rate_limit import LoginRateLimiter
from app.api.deps import get_db
from app.core.config import Settings, settings
from app.main import create_app
from app.models import LoginAttempt, RequestLimit


@pytest.fixture()
def limited_app(monkeypatch, db_engine, testing_session_maker):
    monkeypatch.setattr(settings, "request_limit_per_minute", 3)
    monkeypatch.setattr(settings, "registration_limit_per_minute", 2)
    app = create_app(db_engine=db_engine, session_maker=testing_session_maker)

    def isolated_db():
        with testing_session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = isolated_db
    return app


def test_general_limit_and_expiry(limited_app, monkeypatch):
    monkeypatch.setattr("app.admin.rate_limit.time.time", lambda: 10000)
    with TestClient(limited_app) as client:
        for _ in range(3):
            assert client.get("/").status_code == 200
        response = client.get("/", headers={"Accept": "application/json"})
        assert response.status_code == 429
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert response.headers["retry-after"] == "60"
        assert "Слишком много запросов" in response.json()["detail"]
        # Forged forwarding headers cannot allocate another client's quota.
        assert (
            client.get("/", headers={"X-Forwarded-For": "192.0.2.4"}).status_code == 429
        )
        assert client.get("/api/v1/health").status_code == 200
        assert client.get("/static/css/app.css").status_code == 200
        monkeypatch.setattr("app.admin.rate_limit.time.time", lambda: 10060)
        assert client.get("/").status_code == 200


def test_form_limit_is_shared_between_competitions(limited_app):
    with TestClient(limited_app) as client:
        assert client.post("/competitions/missing/register").status_code == 404
        assert client.post("/competitions/other/register").status_code == 404
        response = client.post("/competitions/third/register")
        assert response.status_code == 429
        assert response.headers["retry-after"]


def test_ip_limits_do_not_depend_on_cookies(limited_app):
    with TestClient(limited_app, client=("192.0.2.1", 1234)) as first:
        for _ in range(3):
            assert first.get("/").status_code == 200
    with TestClient(limited_app, client=("192.0.2.1", 9999)) as same_ip:
        assert same_ip.get("/").status_code == 429
    with TestClient(limited_app, client=("192.0.2.2", 1234)) as other:
        assert other.get("/").status_code == 200


def production_settings(**overrides):
    values = dict(
        database_url="sqlite://",
        app_debug=False,
        database_echo=False,
        secret_key="s" * 64,
        production=True,
        render=False,
        public_base_url="https://club.example",
        captcha_enabled=True,
        smartcaptcha_client_key="ysc1_test-only-public",
        smartcaptcha_server_key=SecretStr("ysc2_test-only-private"),
        smartcaptcha_allowed_hosts="club.example",
    )
    return Settings(_env_file=None, **{**values, **overrides})


@pytest.mark.parametrize(
    "overrides",
    [
        {"public_base_url": "http://club.example"},
        {"public_base_url": "https://club.example/path"},
        {"public_base_url": "https://user:password@club.example"},
        {"captcha_enabled": False},
        {"smartcaptcha_server_key": ""},
        {"smartcaptcha_client_key": "incorrect"},
        {"smartcaptcha_allowed_hosts": "other.example"},
        {"secret_key": "change_me"},
        {"app_debug": True},
        {"database_echo": True},
    ],
)
def test_incomplete_production_configuration_is_rejected(overrides):
    with pytest.raises(ValueError):
        production_settings(**overrides).validate_production()


@pytest.mark.parametrize("render", [False, True])
def test_https_redirect_secure_cookie_hsts_and_trusted_host(
    monkeypatch,
    db_engine,
    testing_session_maker,
    render,
):
    config = production_settings(
        production=not render,
        render=render,
        public_base_url="" if render else "https://club.example",
        render_external_url="https://club.example" if render else "",
        session_cookie_secure=False,
    )
    for name in type(config).model_fields:
        monkeypatch.setattr(settings, name, getattr(config, name))
    app = create_app(db_engine=db_engine, session_maker=testing_session_maker)
    with TestClient(app, base_url="https://club.example") as client:
        login = client.get("/admin/login")
        assert login.status_code == 200
        cookie = login.headers["set-cookie"].lower()
        assert "secure" in cookie and "httponly" in cookie and "samesite=lax" in cookie
        assert login.headers["strict-transport-security"] == "max-age=31536000"
        redirect = client.get("http://club.example/", follow_redirects=False)
        assert redirect.status_code == 307
        assert redirect.headers["x-frame-options"] == "DENY"
        assert redirect.headers["location"] == "https://club.example/"
        assert "strict-transport-security" not in redirect.headers
        assert (
            client.get("https://evil.example/", follow_redirects=False).status_code
            == 400
        )


def test_public_cleanup_never_resets_admin_login_limit(
    monkeypatch,
    testing_session_maker,
):
    monkeypatch.setattr("app.admin.rate_limit.time.time", lambda: 10000)
    login = LoginRateLimiter(
        testing_session_maker,
        "secret",
        account_limit=5,
        ip_limit=30,
        window_seconds=900,
    )
    login.consume("admin", "192.0.2.1")
    monkeypatch.setattr("app.admin.rate_limit.time.time", lambda: 10100)
    monkeypatch.setattr("app.admin.rate_limit.secrets.randbelow", lambda *args: 0)
    public = LoginRateLimiter(
        testing_session_maker,
        "secret",
        account_limit=1,
        ip_limit=1,
        window_seconds=60,
        counter_table=RequestLimit.__table__,
    )
    public.consume_buckets((("web:ip", "192.0.2.1", 120),))
    with testing_session_maker() as session:
        assert len(session.scalars(select(LoginAttempt)).all()) == 2
