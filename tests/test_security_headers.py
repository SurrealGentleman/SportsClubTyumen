from html.parser import HTMLParser
import re

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.db.dependencies import get_db
from app.main import create_app
from tests.admin_helpers import admin_login
from tests.factories import create_admin, create_individual_competition


class ScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.event_handlers = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.scripts.append(attrs)
        self.event_handlers.extend(name for name in attrs if name.startswith("on"))


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/admin/login",
        "/api/v1/health",
        "/static/css/app.css",
        "/missing-page",
    ],
)
def test_headers_cover_pages_assets_api_errors_and_docs(client, path):
    response = client.get(path)
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response.headers["permissions-policy"]
    policy = response.headers["content-security-policy"]
    assert "frame-ancestors 'none'" in policy
    assert "object-src 'none'" in policy
    assert "script-src-attr 'none'" in policy
    assert "'unsafe-eval'" not in policy
    assert "'unsafe-inline'" not in policy.split("script-src ")[1].split(";")[0]
    assert "strict-transport-security" not in response.headers


def test_headers_cover_uncaught_500(test_app, monkeypatch):
    monkeypatch.setattr(settings, "app_debug", False)
    test_app.debug = False

    @test_app.get("/test-error")
    def fail():
        raise RuntimeError("test failure")

    with TestClient(test_app, raise_server_exceptions=False) as client:
        response = client.get("/test-error")
    assert response.status_code == 500
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_csp_profiles_do_not_share_external_script_permissions(client):
    public = client.get("/").headers["content-security-policy"]
    admin = client.get("/admin/login").headers["content-security-policy"]
    assert "bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js" in public
    assert "script-src 'self';" in admin
    assert "jsdelivr" not in admin and "smartcaptcha" not in admin
    assert "smartcaptcha" not in public
    connections = public.split("connect-src ", 1)[1].split(";", 1)[0].split()
    assert (
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js.map"
        in connections
    )
    assert (
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css.map"
        in connections
    )
    assert "https://cdn.jsdelivr.net" not in connections
    assert ".map" not in admin


def test_admin_current_forms_have_no_inline_scripts_or_event_handlers(
    client, db_session
):
    create_admin(db_session)
    admin_login(client, data={"username": "admin", "password": "strong-admin-password"})
    for path in (
        "/admin/",
        "/admin/sport/create",
        "/admin/training/create",
        "/admin/competition/create",
        "/admin/sport/list",
    ):
        response = client.get(path)
        parser = ScriptParser()
        parser.feed(response.text)
        assert parser.scripts and all(script.get("src") for script in parser.scripts)
        assert not parser.event_handlers
        assert "admin-flash.js" in response.text


@pytest.mark.parametrize("path", ["/docs", "/docs/oauth2-redirect", "/redoc"])
def test_docs_inline_initializers_have_matching_random_nonce(client, path):
    first = client.get(path)
    second = client.get(path)
    policy = first.headers["content-security-policy"]
    nonce = re.search(r"'nonce-([^']+)'", policy)[1]
    assert f"'nonce-{nonce}'" not in second.headers["content-security-policy"]
    parser = ScriptParser()
    parser.feed(first.text)
    assert all(s.get("src") or s.get("nonce") == nonce for s in parser.scripts)
    assert first.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("report_only", [False, True])
def test_captcha_profile_can_be_staged_then_enforced(
    monkeypatch,
    db_engine,
    testing_session_maker,
    db_session,
    report_only,
):
    monkeypatch.setattr(settings, "captcha_enabled", True)
    monkeypatch.setattr(settings, "csp_captcha_report_only", report_only)
    monkeypatch.setattr(settings, "smartcaptcha_client_key", "ysc1_test-only")
    monkeypatch.setattr(
        settings, "smartcaptcha_server_key", SecretStr("ysc2_test-only")
    )
    monkeypatch.setattr(settings, "smartcaptcha_allowed_hosts", "testserver")
    app = create_app(db_engine=db_engine, session_maker=testing_session_maker)
    # The middleware must select the profile even for a 404 or rejected form.
    with TestClient(app) as client:
        response = client.post(
            "/competitions/missing/other/register", follow_redirects=False
        )
        policy = (
            response.headers.get("content-security-policy-report-only")
            if report_only
            else (response.headers["content-security-policy"])
        )
        assert "https://smartcaptcha.cloud.yandex.ru" in policy
        assert "https://smartcaptcha.yandexcloud.net" in policy
        if report_only:
            assert (
                "frame-ancestors 'none'" in response.headers["content-security-policy"]
            )
            assert "script-src" not in response.headers["content-security-policy"]
        else:
            assert "content-security-policy-report-only" not in response.headers


def test_real_captcha_markup_and_csp_origins_agree(
    db_engine, testing_session_maker, db_session, monkeypatch
):
    create_individual_competition(db_session)
    monkeypatch.setattr(settings, "captcha_enabled", True)
    monkeypatch.setattr(settings, "smartcaptcha_client_key", "ysc1_test-only")
    monkeypatch.setattr(
        settings, "smartcaptcha_server_key", SecretStr("ysc2_test-only")
    )
    monkeypatch.setattr(settings, "smartcaptcha_allowed_hosts", "testserver")
    app = create_app(db_engine=db_engine, session_maker=testing_session_maker)

    def isolated_db():
        with testing_session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = isolated_db
    with TestClient(app) as client:
        response = client.get("/competitions/individual-cup/register")
    assert 'src="https://smartcaptcha.cloud.yandex.ru/captcha.js"' in response.text
    assert (
        "smartcaptcha.cloud.yandex.ru"
        in response.headers["content-security-policy-report-only"]
    )
