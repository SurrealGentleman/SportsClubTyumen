"""Response hardening, with separate CSP profiles for pages, admin and API docs."""

import secrets

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send


BASE_POLICY = (
    "base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'"
)
CAPTCHA_ORIGINS = (
    "https://smartcaptcha.cloud.yandex.ru https://smartcaptcha.yandexcloud.net"
)
BOOTSTRAP_CSS = (
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css"
)
BOOTSTRAP_JS = (
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/js/bootstrap.bundle.min.js"
)


def content_security_policy(path: str, nonce: str, *, captcha: bool) -> str:
    scripts = "'self'"
    styles = "'self' 'unsafe-inline'"
    images = "'self' data:"
    fonts = "'self' data:"
    connections = "'self'"
    frames = "'none'"
    workers = "'none'"
    if path in {"/docs", "/docs/oauth2-redirect", "/redoc"}:
        # Only trusted FastAPI-generated inline initializers receive this nonce.
        scripts += f" 'nonce-{nonce}' https://cdn.jsdelivr.net"
        styles += " https://cdn.jsdelivr.net https://fonts.googleapis.com"
        images += (
            " https://fastapi.tiangolo.com https://cdn.redoc.ly/redoc/logo-mini.svg"
        )
        fonts += " https://fonts.gstatic.com"
        workers = "'self' blob:"
    elif path == "/admin" or path.startswith("/admin/"):
        pass  # SQLAdmin assets are served locally; no CDN or CAPTCHA privileges.
    else:
        scripts += f" {BOOTSTRAP_JS}"
        styles += f" {BOOTSTRAP_CSS}"
        if captcha:
            scripts += f" {CAPTCHA_ORIGINS}"
            connections += f" {CAPTCHA_ORIGINS}"
            images += f" {CAPTCHA_ORIGINS}"
            frames = CAPTCHA_ORIGINS
    return (
        f"default-src 'none'; {BASE_POLICY}; script-src {scripts}; "
        f"script-src-attr 'none'; style-src {styles}; img-src {images}; "
        f"font-src {fonts}; connect-src {connections}; frame-src {frames}; "
        f"worker-src {workers}; manifest-src 'self'"
    )


class SecurityHeadersMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        https: bool,
        report_only: bool,
        captcha_report_only: bool,
        captcha_enabled: bool,
    ) -> None:
        self.app = app
        self.https = https
        self.report_only = report_only
        self.captcha_report_only = captcha_report_only
        self.captcha_enabled = captcha_enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        nonce = secrets.token_urlsafe(32)
        scope.setdefault("state", {})["csp_nonce"] = nonce
        path = scope["path"]
        captcha = (
            self.captcha_enabled
            and path.startswith("/competitions/")
            and (path.rstrip("/").endswith("/register"))
        )
        policy = content_security_policy(path, nonce, captcha=captcha)
        report_only = self.report_only or (captcha and self.captcha_report_only)

        async def harden(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["x-content-type-options"] = "nosniff"
                headers["x-frame-options"] = "DENY"
                headers["referrer-policy"] = "strict-origin-when-cross-origin"
                headers["permissions-policy"] = (
                    "camera=(), microphone=(), geolocation=()"
                )
                headers["x-xss-protection"] = "0"
                headers["content-security-policy"] = (
                    BASE_POLICY if report_only else policy
                )
                if report_only:
                    headers["content-security-policy-report-only"] = policy
                if self.https and scope.get("scheme") == "https":
                    headers["strict-transport-security"] = "max-age=31536000"
                if path in {"/docs", "/docs/oauth2-redirect", "/redoc"}:
                    # Cached nonced HTML must not be mixed with fresh CSP headers.
                    headers["cache-control"] = "no-store"
            await send(message)

        await self.app(scope, receive, harden)
