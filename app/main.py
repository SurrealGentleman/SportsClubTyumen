from fastapi import FastAPI
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.staticfiles import StaticFiles
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.types import ASGIApp
from urllib.parse import urlsplit

from app.admin.setup import setup_admin
from app.admin.rate_limit import LoginRateLimiter
from app.api.router import router as api_router
from app.core.config import settings
from app.core.error_pages import setup_error_handlers
from app.core.http_security import RequestLimitMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.core.api_docs import setup_api_docs
from app.core.templating import templates
from app.db.session import SessionLocal, engine
from app.models import RequestLimit
from app.routers import router as public_router


class SecureFastAPI(FastAPI):
    def build_middleware_stack(self) -> ASGIApp:
        # Wrap ServerErrorMiddleware too: redirects, 400/403/429 and unhandled
        # 500 responses must receive the same protection as normal pages.
        return SecurityHeadersMiddleware(
            super().build_middleware_stack(),
            https=settings.https_deployment,
            report_only=settings.csp_report_only,
            captcha_report_only=settings.csp_captcha_report_only,
            captcha_enabled=settings.captcha_enabled and settings.captcha_ready,
        )


def create_app(
    db_engine: Engine = engine,
    session_maker: sessionmaker[Session] = SessionLocal,
) -> FastAPI:
    settings.validate_production()
    app = SecureFastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
        docs_url=None,
        redoc_url=None,
    )
    setup_api_docs(app)

    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(public_router)
    app.include_router(api_router, prefix="/api/v1")
    setup_error_handlers(app, templates)
    setup_admin(app, db_engine=db_engine, session_maker=session_maker)

    app.add_middleware(
        RequestLimitMiddleware,
        limiter=LoginRateLimiter(
            session_maker,
            settings.secret_key,
            account_limit=1,
            ip_limit=1,
            window_seconds=60,
            counter_table=RequestLimit.__table__,
        ),
        request_limit=settings.request_limit_per_minute,
        registration_limit=settings.registration_limit_per_minute,
    )
    if settings.https_deployment:
        app.add_middleware(HTTPSRedirectMiddleware)
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=[urlsplit(settings.external_url).hostname],
            www_redirect=False,
        )

    return app


app = create_app()
