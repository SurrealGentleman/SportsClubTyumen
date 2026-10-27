from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqladmin import Admin as SQLAdmin, I18nConfig
from sqladmin.authentication import login_required
from starlette.exceptions import HTTPException

from app.admin.auth import AdminAuthentication
from app.admin.csrf import admin_csrf_token
from app.admin.views import ADMIN_VIEWS
from app.core.config import settings
from app.core.time import APP_TIMEZONE
from app.models import Competition, Registration, Sport, Training


class SportsClubAdmin(SQLAdmin):
    async def login(self, request: Request):  # type: ignore[no-untyped-def]
        try:
            return await super().login(request)
        except HTTPException as exc:
            if exc.status_code != 429:
                raise
            response = await self.templates.TemplateResponse(
                request, "sqladmin/login.html", {"error": exc.detail}, status_code=429
            )
            response.headers.update(exc.headers or {})
            return response

    @login_required
    async def index(self, request: Request):  # type: ignore[no-untyped-def]
        with self.session_maker() as session:
            dashboard = {
                "sports": session.scalar(select(func.count()).select_from(Sport)) or 0,
                "trainings": session.scalar(
                    select(func.count())
                    .select_from(Training)
                    .where(Training.is_active.is_(True))
                )
                or 0,
                "competitions": session.scalar(
                    select(func.count())
                    .select_from(Competition)
                    .where(Competition.end_date >= datetime.now(APP_TIMEZONE).date())
                )
                or 0,
                "registrations": session.scalar(
                    select(func.count()).select_from(Registration)
                )
                or 0,
            }
        return await self.templates.TemplateResponse(
            request,
            "sqladmin/index.html",
            {
                "title": "Панель управления",
                "subtitle": "Спортивный клуб ТюмГУ",
                "dashboard": dashboard,
            },
        )


def setup_admin(
    app: FastAPI,
    *,
    db_engine: Engine,
    session_maker: sessionmaker[Session],
) -> SQLAdmin:
    authentication_backend = AdminAuthentication(
        secret_key=settings.secret_key,
        session_maker=session_maker,
        https_only=settings.session_cookie_secure,
    )
    admin = SportsClubAdmin(
        app=app,
        engine=db_engine,
        session_maker=session_maker,
        title="Спортивный клуб ТюмГУ",
        templates_dir=str(Path(__file__).parent.parent / "templates"),
        authentication_backend=authentication_backend,
        i18n_config=I18nConfig(
            default_locale="ru",
            language_cookie_name=None,
            language_header_name=None,
        ),
    )

    for view in ADMIN_VIEWS:
        admin.add_view(view)

    admin.templates.env.globals["admin_csrf_token"] = admin_csrf_token
    for route in admin.admin.routes:
        if route.name == "logout":
            route.methods = {"POST"}

    return admin
