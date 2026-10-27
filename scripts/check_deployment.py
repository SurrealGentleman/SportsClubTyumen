"""Check deployment settings without printing keys or connecting to the DB."""

import json

from pydantic import ValidationError


def main() -> int:
    # Settings are constructed during import. Catch parsing failures as well as
    # production policy errors without exposing input values in a traceback.
    try:
        from app.core.config import settings
    except ValidationError as exc:
        print(
            json.dumps(
                {
                    "configuration_error": "Некорректные переменные окружения.",
                    "invalid_fields": [
                        ".".join(str(part) for part in error["loc"])
                        for error in exc.errors(include_input=False, include_url=False)
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    checks = {
        "production": settings.production,
        "https_enabled": settings.https_deployment,
        "secure_cookie": settings.secure_cookies,
        "public_url_configured": bool(settings.external_url),
        "captcha_enabled": settings.captcha_enabled,
        "captcha_keys_and_hosts_present": settings.captcha_ready,
        "request_limit_per_minute": settings.request_limit_per_minute,
        "registration_limit_per_minute": settings.registration_limit_per_minute,
        "admin_login_account_limit": settings.admin_login_account_limit,
        "admin_login_ip_limit": settings.admin_login_ip_limit,
        "admin_login_window_seconds": settings.admin_login_window_seconds,
        "csp_enforced": not settings.csp_report_only,
        "captcha_csp_enforced": not settings.csp_captcha_report_only,
    }
    try:
        settings.validate_production()
    except ValueError as exc:
        checks["configuration_error"] = str(exc)
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    return (
        0
        if (
            settings.production
            and settings.captcha_enabled
            and settings.captcha_ready
            and "configuration_error" not in checks
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
