"""Deployment diagnostics are offline, machine-readable and redact secrets."""

import json
import os
import re
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from scripts.check_deployment import main


def test_production_env_example_contains_all_application_settings():
    template = (
        Path(__file__).resolve().parents[1] / "deploy/production.env.example"
    ).read_text(encoding="utf-8")
    names = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", template, re.MULTILINE))
    assert {name.upper() for name in Settings.model_fields} <= names
    assert {
        "DOMAIN",
        "ACME_EMAIL",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "POSTGRES_DB",
    } <= names


@pytest.fixture()
def deployment_settings(monkeypatch):
    config = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:private-db-password@db.invalid/club",
        secret_key="private-session-secret-" * 3,
        app_debug=False,
        database_echo=False,
        production=True,
        public_base_url="https://club.example",
        captcha_enabled=True,
        smartcaptcha_client_key="ysc1_test-public-key",
        smartcaptcha_server_key=SecretStr("ysc2_test-private-key"),
        smartcaptcha_allowed_hosts="club.example",
        request_limit_per_minute=120,
        registration_limit_per_minute=10,
        admin_login_account_limit=5,
        admin_login_ip_limit=30,
        admin_login_window_seconds=900,
        csp_report_only=False,
        csp_captcha_report_only=True,
    )
    monkeypatch.setattr("app.core.config.settings", config)
    return config


def assert_redacted(output, config):
    for secret in (
        config.database_url,
        "private-db-password",
        config.secret_key,
        config.smartcaptcha_server_key.get_secret_value(),
    ):
        if secret:
            assert secret not in output


def test_production_check_is_offline_and_reports_limits(
    deployment_settings, monkeypatch, capsys
):
    def forbid_connection(*args, **kwargs):
        raise AssertionError("Deployment diagnostics must not contact DB or CAPTCHA")

    monkeypatch.setattr("sqlalchemy.create_engine", forbid_connection)
    monkeypatch.setattr("socket.create_connection", forbid_connection)
    assert main() == 0
    captured = capsys.readouterr()
    assert not captured.err
    assert_redacted(captured.out, deployment_settings)
    report = json.loads(captured.out)
    assert report["production"] is True
    assert report["https_enabled"] is True
    assert report["secure_cookie"] is True
    assert report["captcha_keys_and_hosts_present"] is True
    assert report["request_limit_per_minute"] == 120
    assert report["registration_limit_per_minute"] == 10
    assert report["admin_login_account_limit"] == 5
    assert report["admin_login_ip_limit"] == 30
    assert report["admin_login_window_seconds"] == 900
    assert report["csp_enforced"] is True
    assert report["captcha_csp_enforced"] is False
    assert "configuration_error" not in report


@pytest.mark.parametrize(
    "changes",
    [
        {"production": False},
        {"captcha_enabled": False},
        {"smartcaptcha_server_key": SecretStr("")},
        {"smartcaptcha_allowed_hosts": "other.example"},
        {"app_debug": True},
        {"public_base_url": "https://user:private-url-password@club.example"},
        {"public_base_url": "https://user:private-url-password@club.example／evil"},
    ],
)
def test_incomplete_configuration_has_nonzero_status_without_secrets(
    deployment_settings, capsys, changes
):
    for name, value in changes.items():
        setattr(deployment_settings, name, value)
    assert main() == 1
    captured = capsys.readouterr()
    assert not captured.err
    report = json.loads(captured.out)
    if deployment_settings.production:
        assert report["configuration_error"]
    assert_redacted(captured.out, deployment_settings)
    assert "private-url-password" not in captured.out


@pytest.mark.parametrize("field", ["REQUEST_LIMIT_PER_MINUTE", "DATABASE_ECHO"])
def test_invalid_environment_is_reported_without_values_or_traceback(field):
    marker = "invalid-value-that-must-not-be-disclosed"
    environment = {**os.environ, field: marker, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, "-m", "scripts.check_deployment"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 1
    assert not result.stderr
    assert marker not in result.stdout
    report = json.loads(result.stdout)
    assert report["configuration_error"]
    assert field.lower() in report["invalid_fields"]
