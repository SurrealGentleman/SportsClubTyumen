from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.db.dependencies import SessionDep
from app.core.templating import templates
from app.models import Sport

router = APIRouter(include_in_schema=False)


@router.get("/schedule", response_class=HTMLResponse, name="schedule")
def schedule(request: Request, db: SessionDep) -> HTMLResponse:
    sports = db.scalars(
        select(Sport).where(Sport.is_active.is_(True)).order_by(Sport.name)
    ).all()
    return templates.TemplateResponse(
        request,
        "schedule.html",
        {"sports": sports},
    )


@router.get("/sports/{slug}", response_class=HTMLResponse, name="sport_detail")
def sport_detail(slug: str, request: Request, db: SessionDep) -> HTMLResponse:
    sport = db.scalar(
        select(Sport)
        .options(selectinload(Sport.trainings))
        .where(Sport.slug == slug, Sport.is_active.is_(True))
    )
    if sport is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    trainings = sorted(
        (training for training in sport.trainings if training.is_active),
        key=lambda training: (
            training.group_name.value.casefold(),
            training.weekday,
            training.start_time,
        ),
    )
    return templates.TemplateResponse(
        request,
        "sport.html",
        {"sport": sport, "trainings": trainings},
    )
