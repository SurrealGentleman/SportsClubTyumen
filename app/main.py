from fastapi import FastAPI
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.staticfiles import StaticFiles

from app.admin.setup import setup_admin
from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.db.session import SessionLocal, engine
from app.routers.pages import router as pages_router


def create_app(
    db_engine: Engine = engine,
    session_maker: sessionmaker[Session] = SessionLocal,
) -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
    )

    app.mount("/static", StaticFiles(directory="app/static"), name="static")
    app.include_router(pages_router)
    app.include_router(api_v1_router, prefix="/api/v1")
    setup_admin(app, db_engine=db_engine, session_maker=session_maker)

    return app


app = create_app()
