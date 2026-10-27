"""Public HTML routers. Keep URLs and route names stable for templates."""

from fastapi import APIRouter

from app.routers.competitions import router as competitions_router
from app.routers.home import router as home_router
from app.routers.legal import router as legal_router
from app.routers.registrations import router as registrations_router
from app.routers.schedule import router as schedule_router

router = APIRouter(include_in_schema=False)

# Preserve the original registration order and names from pages.py.
router.include_router(legal_router)
router.include_router(home_router)
router.include_router(schedule_router)
router.include_router(competitions_router)
router.include_router(registrations_router)
