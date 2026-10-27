"""Shared public template environment, independent of route registration."""

from datetime import date, datetime
from pathlib import Path

from starlette.templating import Jinja2Templates

from app.core.branding import BRAND_ASSETS
from app.core.privacy import CONSENT_DOCUMENT_TEMPLATE, CONSENT_VERSION
from app.core.time import local_datetime
from app.models.training import WEEKDAY_NAMES

templates = Jinja2Templates(
    directory=Path(__file__).resolve().parent.parent / "templates"
)

MONTH_NAMES = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def format_date(value: date | datetime) -> str:
    if isinstance(value, datetime):
        value = local_datetime(value)
    return f"{value.day} {MONTH_NAMES[value.month]} {value.year}"


def format_datetime(value: datetime) -> str:
    value = local_datetime(value)
    return f"{format_date(value)}, {value:%H:%M}"


templates.env.filters["date_ru"] = format_date
templates.env.filters["datetime_ru"] = format_datetime
templates.env.globals["weekday_names"] = WEEKDAY_NAMES
templates.env.globals["brand_assets"] = BRAND_ASSETS
templates.env.globals["consent_document_template"] = CONSENT_DOCUMENT_TEMPLATE
templates.env.globals["consent_version"] = CONSENT_VERSION
