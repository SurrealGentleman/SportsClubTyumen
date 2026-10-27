import json
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from app.core.config import settings

VALIDATION_URL = "https://smartcaptcha.cloud.yandex.ru/validate"
MAX_TOKEN_LENGTH = 8192
MAX_RESPONSE_LENGTH = 4096
VALIDATION_TIMEOUT = 5


class CaptchaError(Exception):
    status_code = 422
    message = "Пройдите проверку «Я не робот» и отправьте заявку снова."


class CaptchaUnavailableError(CaptchaError):
    status_code = 503
    message = "Проверка «Я не робот» временно недоступна. Попробуйте позже."


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_smartcaptcha(token: str, expected_host: str) -> None:
    if not settings.captcha_enabled:
        return
    if not settings.captcha_ready:
        raise CaptchaUnavailableError
    host = expected_host.strip().lower()
    if host not in settings.captcha_allowed_hosts:
        raise CaptchaUnavailableError
    if not token or len(token) > MAX_TOKEN_LENGTH:
        raise CaptchaError

    body = urlencode(
        {
            "secret": settings.smartcaptcha_server_key.get_secret_value(),
            "token": token,
        }
    ).encode("utf-8")
    request = Request(
        VALIDATION_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        # Never forward the server key to a redirect target.
        with build_opener(NoRedirects()).open(
            request, timeout=VALIDATION_TIMEOUT
        ) as response:
            if response.status != 200:
                raise CaptchaUnavailableError
            raw = response.read(MAX_RESPONSE_LENGTH + 1)
        if len(raw) > MAX_RESPONSE_LENGTH:
            raise CaptchaUnavailableError
        result = json.loads(raw)
    except (URLError, OSError, ValueError) as exc:
        raise CaptchaUnavailableError from exc
    if not isinstance(result, dict):
        raise CaptchaUnavailableError
    if result.get("status") != "ok":
        raise CaptchaError
    result_host = result.get("host")
    if not isinstance(result_host, str) or result_host.lower() != host:
        raise CaptchaError
