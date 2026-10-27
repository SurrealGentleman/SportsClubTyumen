from fastapi import FastAPI
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.staticfiles import StaticFiles
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from urllib.parse import urlsplit

from app.admin.setup import setup_admin
from app.admin.rate_limit import LoginRateLimiter
from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.core.error_pages import setup_error_handlers
from app.core.http_security import HSTSMiddleware, RequestLimitMiddleware
from app.db.session import SessionLocal, engine
from app.models import RequestLimit
from app.routers.pages import router as pages_router
from app.routers.pages import templates


def create_app(
    db_engine: Engine = engine,
    session_maker: sessionmaker[Session] = SessionLocal,
) -> FastAPI:
    settings.validate_production()
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
    )

    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(pages_router)
    app.include_router(api_v1_router, prefix="/api/v1")
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
        app.add_middleware(HSTSMiddleware)
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=[urlsplit(settings.external_url).hostname],
            www_redirect=False,
        )

    return app


app = create_app()
