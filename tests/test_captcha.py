import json
from urllib.parse import parse_qs

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Registration
from app.services import captcha
from tests.test_registrations import create_individual_competition, valid_payload
from tests.test_team_registrations import create_team_competition, team_payload


class ValidationResponse:
    def __init__(self, content: bytes, status: int = 200) -> None:
        self.content = content
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit: int) -> bytes:
        return self.content[:limit]


@pytest.fixture()
def captcha_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "captcha_enabled", True)
    monkeypatch.setattr(settings, "smartcaptcha_client_key", "ysc1_public-test-key")
    monkeypatch.setattr(
        settings, "smartcaptcha_server_key", SecretStr("ysc2_private-test-key")
    )
    monkeypatch.setattr(settings, "smartcaptcha_allowed_hosts", "testserver")


@pytest.fixture(params=[False, True])
def captcha_form(
    request: pytest.FixtureRequest, db_session: Session
) -> tuple[str, dict]:
    if request.param:
        create_team_competition(db_session)
        return "/competitions/team-cup/register", team_payload(
            ["member1@study.utmn.ru", "member2@study.utmn.ru"]
        )
    create_individual_competition(db_session)
    return "/competitions/individual-cup/register", valid_payload()


def mock_validator(monkeypatch: pytest.MonkeyPatch, responses: list[object]) -> list:
    calls = []

    class Opener:
        def open(self, request, timeout):
            calls.append(request)
            assert request.full_url == captcha.VALIDATION_URL
            assert timeout == captcha.VALIDATION_TIMEOUT
            assert request.get_method() == "POST"
            body = parse_qs(request.data.decode())
            assert set(body) == {"secret", "token"}
            assert body["secret"] == ["ysc2_private-test-key"]
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

    monkeypatch.setattr(captcha, "build_opener", lambda *handlers: Opener())
    return calls


def test_captcha_widget_contains_only_the_public_key(
    client: TestClient, captcha_settings: None, captcha_form: tuple[str, dict]
) -> None:
    path, _ = captcha_form
    response = client.get(path)

    assert response.status_code == 200
    assert "https://smartcaptcha.cloud.yandex.ru/captcha.js" in response.text
    assert "/static/js/captcha-fit.js" in response.text
    assert 'data-sitekey="ysc1_public-test-key"' in response.text
    assert "ysc2_private-test-key" not in response.text


@pytest.mark.parametrize("token", [None, "", ["token-one", "token-two"]])
def test_missing_or_ambiguous_token_cannot_create_a_registration(
    client: TestClient,
    db_session: Session,
    captcha_settings: None,
    captcha_form: tuple[str, dict],
    monkeypatch: pytest.MonkeyPatch,
    token: object,
) -> None:
    path, payload = captcha_form
    if token is not None:
        payload["smart-token"] = token
    calls = mock_validator(monkeypatch, [])

    response = client.post(path, data=payload)

    assert response.status_code == 422
    assert "Пройдите проверку «Я не робот»" in response.text
    assert calls == []
    assert db_session.scalar(select(func.count()).select_from(Registration)) == 0


@pytest.mark.parametrize(
    ("result", "status_code"),
    [
        (ValidationResponse(b'{"status":"failed"}'), 422),
        (ValidationResponse(b'{"status":"ok","host":"attacker.example"}'), 422),
        (ValidationResponse(b'{"status":"ok","host":""}'), 422),
        (ValidationResponse(b"not-json"), 503),
        (ValidationResponse(b"[]"), 503),
        (ValidationResponse(b"{}", status=500), 503),
        (ValidationResponse(b"x" * 5000), 503),
        (TimeoutError("validation timed out"), 503),
    ],
)
def test_failed_captcha_or_provider_outage_never_saves_data(
    client: TestClient,
    db_session: Session,
    captcha_settings: None,
    captcha_form: tuple[str, dict],
    monkeypatch: pytest.MonkeyPatch,
    result: object,
    status_code: int,
) -> None:
    path, payload = captcha_form
    payload["smart-token"] = "submitted-token"
    calls = mock_validator(monkeypatch, [result])

    response = client.post(path, data=payload)

    assert response.status_code == status_code
    assert len(calls) == 1
    assert "submitted-token" not in response.text
    assert "ysc2_private-test-key" not in response.text
    assert db_session.scalar(select(func.count()).select_from(Registration)) == 0


def test_verified_captcha_allows_registration(
    client: TestClient,
    db_session: Session,
    captcha_settings: None,
    captcha_form: tuple[str, dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, payload = captcha_form
    payload["smart-token"] = "verified-token"
    mock_validator(
        monkeypatch,
        [
            ValidationResponse(
                json.dumps({"status": "ok", "host": "testserver"}).encode()
            )
        ],
    )

    response = client.post(path, data=payload)

    assert response.status_code == 201
    assert db_session.scalar(select(func.count()).select_from(Registration)) == 1


def test_unconfigured_captcha_blocks_form_and_direct_post(
    client: TestClient,
    db_session: Session,
    captcha_settings: None,
    captcha_form: tuple[str, dict],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path, payload = captcha_form
    monkeypatch.setattr(settings, "smartcaptcha_server_key", SecretStr(""))
    calls = mock_validator(monkeypatch, [])

    form_response = client.get(path)
    response = client.post(path, data=payload)

    assert "Подача заявок временно недоступна" in form_response.text
    assert 'type="submit" disabled' in form_response.text
    assert "smartcaptcha.cloud.yandex.ru/captcha.js" not in form_response.text
    assert response.status_code == 503
    assert calls == []
    assert db_session.scalar(select(func.count()).select_from(Registration)) == 0


def test_token_is_checked_again_on_every_submission(
    client: TestClient,
    db_session: Session,
    captcha_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    create_individual_competition(db_session)
    path = "/competitions/individual-cup/register"
    first = valid_payload("first@study.utmn.ru")
    second = valid_payload("second@study.utmn.ru")
    first["smart-token"] = second["smart-token"] = "one-time-token"
    calls = mock_validator(
        monkeypatch,
        [
            ValidationResponse(b'{"status":"ok","host":"testserver"}'),
            ValidationResponse(
                b'{"status":"failed","message":"Invalid or expired Token."}'
            ),
        ],
    )

    assert client.post(path, data=first).status_code == 201
    assert client.post(path, data=second).status_code == 422
    assert len(calls) == 2
    assert db_session.scalar(select(func.count()).select_from(Registration)) == 1


def test_captcha_rejects_unlisted_host_before_network_request(
    captcha_settings: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = mock_validator(monkeypatch, [])

    with pytest.raises(captcha.CaptchaUnavailableError):
        captcha.verify_smartcaptcha("some-token", "unlisted.example")
    assert calls == []
