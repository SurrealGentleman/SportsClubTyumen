"""Contracts preserved when public pages are split into dedicated routers."""

from datetime import date, datetime
from importlib import import_module

import pytest

from app.core.branding import BRAND_ASSETS
from app.core.privacy import CONSENT_VERSION
from app.core.templating import format_date, format_datetime, templates
from app.core.time import APP_TIMEZONE


@pytest.mark.parametrize(
    ("name", "parameters", "path"),
    [
        ("home", {}, "/"),
        ("schedule", {}, "/schedule"),
        ("sport_detail", {"slug": "basketball"}, "/sports/basketball"),
        ("competitions", {}, "/competitions"),
        ("competition_detail", {"slug": "cup"}, "/competitions/cup"),
        ("register_for_competition", {"slug": "cup"}, "/competitions/cup/register"),
        ("submit_registration", {"slug": "cup"}, "/competitions/cup/register"),
        ("personal_data_consent", {}, "/legal/personal-data-consent"),
        ("download_personal_data_consent", {}, "/legal/personal-data-consent/download"),
        ("privacy_policy", {}, "/legal/privacy-policy"),
    ],
)
def test_public_route_names_and_urls_are_preserved(test_app, name, parameters, path):
    assert str(test_app.url_path_for(name, **parameters)) == path


@pytest.mark.parametrize(
    "module", ["home", "schedule", "competitions", "registrations", "legal"]
)
def test_public_routers_share_one_template_environment(module):
    assert import_module(f"app.routers.{module}").templates is templates


def test_template_filters_and_globals_are_preserved():
    assert templates.env.filters["date_ru"] is format_date
    assert templates.env.filters["datetime_ru"] is format_datetime
    assert templates.env.globals["brand_assets"] is BRAND_ASSETS
    assert templates.env.globals["consent_version"] == CONSENT_VERSION
    assert templates.env.globals["weekday_names"][0] == "Понедельник"
    assert format_date(date(2027, 1, 2)) == "2 января 2027"
    assert (
        format_datetime(datetime(2027, 1, 2, 18, 30, tzinfo=APP_TIMEZONE))
        == "2 января 2027, 18:30"
    )


def test_public_html_routes_remain_outside_openapi(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert set(response.json()["paths"]) == {"/api/v1/health"}


def test_legacy_consent_download_redirect_is_preserved(client):
    response = client.get(
        "/legal/personal-data-consent/download", follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("/legal/personal-data-consent")
