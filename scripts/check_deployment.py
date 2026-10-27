"""Check deployment settings without printing keys or connecting to the DB."""

import json

from app.core.config import settings


def main() -> int:
    checks = {
        "production": settings.production,
        "https_enabled": settings.https_deployment,
        "secure_cookie": settings.secure_cookies,
        "public_url_configured": bool(settings.external_url),
        "captcha_enabled": settings.captcha_enabled,
        "captcha_keys_and_hosts_present": settings.captcha_ready,
        "request_limit_per_minute": settings.request_limit_per_minute,
        "registration_limit_per_minute": settings.registration_limit_per_minute,
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
