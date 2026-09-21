from fastapi import FastAPI

from app.api.v1.router import router as api_v1_router
from app.core.config import settings


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.app_debug,
    )

    app.include_router(api_v1_router, prefix="/api/v1")

    return app


app = create_app()
