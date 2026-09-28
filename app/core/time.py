from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


APP_TIMEZONE = ZoneInfo(settings.app_timezone)


def local_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(APP_TIMEZONE)


def local_naive_datetime(value: datetime) -> datetime:
    return local_datetime(value).replace(tzinfo=None)
