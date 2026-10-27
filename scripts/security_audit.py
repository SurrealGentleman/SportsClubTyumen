"""Read local configuration and audit an isolated in-memory application.

Run: poetry run python -m scripts.security_audit
No production database connections or external HTTP requests are made.
"""

import json
import re
import secrets
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.core.config import settings
from app.core.privacy import CONSENT_VERSION
from app.core.security import get_password_hash
from app.db.base import Base
from app.main import create_app
from app.models import Admin, Competition, Registration, RegistrationType, Sport

SECURITY_HEADERS = (
    "Content-Security-Policy",
    "Strict-Transport-Security",
    "X-Content-Type-Options",
    "X-Frame-Options",
    "Referrer-Policy",
    "Permissions-Policy",
)


def audit() -> dict:
    results = {
        "runtime_config": {
            "app_debug": settings.app_debug,
            "session_cookie_secure": settings.session_cookie_secure,
            "effective_secure_cookie": settings.secure_cookies,
            "production": settings.production,
            "render": settings.render,
            "secret_key_is_default": settings.secret_key
            in {"change_me", "change-me-in-production"},
            "captcha_enabled": settings.captcha_enabled,
            "captcha_ready": settings.captcha_ready,
        },
    }
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    sessions = sessionmaker(engine, expire_on_commit=False)
    original_secret = settings.secret_key
    original_captcha = settings.captcha_enabled
    original_production = settings.production
    original_render = settings.render
    settings.secret_key = secrets.token_urlsafe(32)
    # CAPTCHA is tested separately with a mock provider. Disable it only inside
    # this isolated process so SQL payload handling can be audited offline.
    settings.captcha_enabled = False
    # Deployment HTTPS/Host controls are covered by dedicated tests. This local
    # audit uses audit.example, not the real deployment host or CAPTCHA keys.
    settings.production = False
    settings.render = False
    password = secrets.token_urlsafe(24)
    try:
        Base.metadata.create_all(engine)
        with sessions() as session:
            session.add(
                Admin(login="audit-admin", password_hash=get_password_hash(password))
            )
            session.add(
                Admin(login="audit-reviewer", password_hash=get_password_hash(password))
            )
            session.add(
                Competition(
                    title="Audit competition",
                    slug="audit-cup",
                    location="Audit venue",
                    start_date=date.today() + timedelta(days=2),
                    end_date=date.today() + timedelta(days=2),
                    registration_deadline=datetime.now(UTC) + timedelta(days=1),
                    registration_type=RegistrationType.individual,
                    is_registration_open=True,
                    is_published=True,
                )
            )
            session.commit()

        app = create_app(db_engine=engine, session_maker=sessions)
        app.debug = False

        def get_audit_db():
            with sessions() as session:
                yield session

        app.dependency_overrides[get_db] = get_audit_db
        with TestClient(app, base_url="https://audit.example") as client:
            home = client.get("/")
            results["headers_https"] = {
                header: home.headers.get(header) for header in SECURITY_HEADERS
            }
            http_home = client.get("http://audit.example/")
            results["headers_http"] = {
                header: http_home.headers.get(header) for header in SECURITY_HEADERS
            }
            results["headers_by_path_https"] = {}
            for path in (
                "/admin/login",
                "/api/v1/health",
                "/missing-page",
                "/static/css/app.css",
            ):
                response = client.get(path)
                results["headers_by_path_https"][path] = {
                    header: response.headers.get(header) for header in SECURITY_HEADERS
                }

            def csrf_token(path="/admin/login"):
                return re.search(
                    r'name="csrf-token" content="([^"]+)"', client.get(path).text
                )[1]

            token = csrf_token()
            login_injection = client.post(
                "/admin/login",
                data={
                    "username": "' OR '1'='1' --",
                    "password": password,
                    "csrf_token": token,
                },
            )
            results["sql_injection_login"] = {
                "status": login_injection.status_code,
                "authenticated": not client.get(
                    "/admin/", follow_redirects=False
                ).is_redirect,
            }
            attempts = [
                client.post(
                    "/admin/login",
                    data={
                        "username": "audit-admin",
                        "password": "deliberately-wrong-password",
                        "csrf_token": token,
                    },
                ).status_code
                for _ in range(12)
            ]
            login = client.post(
                "/admin/login",
                data={
                    "username": "audit-admin",
                    "password": password,
                    "csrf_token": token,
                },
                follow_redirects=False,
            )
            results["brute_force"] = {
                "failed_attempts": attempts,
                "correct_login_after_attempts": login.status_code,
                "retry_after": login.headers.get("Retry-After"),
            }
            # A distinct account is not blocked by the first account's limit.
            # All data and counters here belong solely to the temporary audit DB.
            reviewer_login = client.post(
                "/admin/login",
                data={
                    "username": "audit-reviewer",
                    "password": password,
                    "csrf_token": token,
                },
                follow_redirects=False,
            )
            assert reviewer_login.status_code == 302
            form = client.get("/admin/sport/create")
            token = csrf_token("/admin/")
            tokenless = client.post(
                "/admin/sport/create",
                data={"name": "Tokenless sport"},
                follow_redirects=False,
            )
            csrf = client.post(
                "/admin/sport/create",
                data={
                    "name": "Audit sport",
                    "is_active": "y",
                    "save": "Сохранить",
                },
                headers={
                    "Origin": "https://untrusted.example",
                    "Sec-Fetch-Site": "cross-site",
                    "X-CSRF-Token": token,
                },
                follow_redirects=False,
            )
            with sessions() as session:
                created = session.scalar(select(func.count()).select_from(Sport))
            results["csrf"] = {
                "csrf_token_in_admin_form": 'name="csrf_token"' in form.text,
                "csrf_token_in_public_form": 'name="csrf_token"'
                in client.get("/competitions/audit-cup/register").text,
                "cross_origin_post_with_session_status": csrf.status_code,
                "tokenless_post_with_session_status": tokenless.status_code,
                "created_records": created,
            }

            payload = "Robert'); DROP TABLE registrations;--"
            bindings = []

            def capture_binding(conn, cursor, statement, parameters, context, many):
                if payload in str(parameters):
                    bindings.append(payload not in statement)

            event.listen(engine, "before_cursor_execute", capture_binding)
            search = client.get("/admin/sport/list", params={"search": payload})
            results["sql_injection_search"] = {
                "status": search.status_code,
                "payload_only_in_bound_parameters": bool(bindings) and all(bindings),
            }
            bindings.clear()
            email = f"audit@{settings.university_email_domain}"
            submitted = client.post(
                "/competitions/audit-cup/register",
                data={
                    "full_name": payload,
                    "university_email": email,
                    "phone": "+7 900 000-00-00",
                    "institute": "Audit institute",
                    "course": "1",
                    "group_name": "audit",
                    "personal_data_consent": "on",
                    "consent_version": CONSENT_VERSION,
                },
            )
            event.remove(engine, "before_cursor_execute", capture_binding)
            with sessions() as session:
                registration = session.scalar(select(Registration))
                literal_saved = (
                    registration is not None and registration.captain_name == payload
                )
            results["sql_injection_registration"] = {
                "status": submitted.status_code,
                "payload_saved_as_literal": literal_saved,
                "payload_only_in_bound_parameters": bool(bindings) and all(bindings),
            }
            logout = client.get(
                "/admin/logout",
                headers={"Sec-Fetch-Site": "cross-site"},
                follow_redirects=False,
            )
            results["csrf"]["logout_via_get_status"] = logout.status_code
            results["csrf"]["session_cleared_by_get"] = client.get(
                "/admin/", follow_redirects=False
            ).is_redirect
            logout_post = client.post(
                "/admin/logout", data={"csrf_token": token}, follow_redirects=False
            )
            results["csrf"]["logout_via_post_status"] = logout_post.status_code
            results["csrf"]["session_cleared_by_post"] = client.get(
                "/admin/", follow_redirects=False
            ).is_redirect
    finally:
        settings.secret_key = original_secret
        settings.captcha_enabled = original_captcha
        settings.production = original_production
        settings.render = original_render
        engine.dispose()
    return results


if __name__ == "__main__":
    print(json.dumps(audit(), ensure_ascii=False, indent=2))
