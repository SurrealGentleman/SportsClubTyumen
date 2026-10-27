from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select

from app.db.dependencies import SessionDep
from app.core.templating import templates
from app.models import Competition
from app.routers._competition_helpers import (
    get_published_competition,
    registration_is_open,
)

router = APIRouter(include_in_schema=False)


@router.get("/competitions", response_class=HTMLResponse, name="competitions")
def competitions(request: Request, db: SessionDep) -> HTMLResponse:
    items = db.scalars(
        select(Competition)
        .where(Competition.is_published.is_(True))
        .order_by(Competition.start_date, Competition.title)
    ).all()
    return templates.TemplateResponse(
        request,
        "competitions.html",
        {
            "competitions": items,
            "registration_is_open": registration_is_open,
        },
    )


@router.get(
    "/competitions/{slug}",
    response_class=HTMLResponse,
    name="competition_detail",
)
def competition_detail(slug: str, request: Request, db: SessionDep) -> HTMLResponse:
    competition = get_published_competition(db, slug)

    return templates.TemplateResponse(
        request,
        "competition.html",
        {
            "competition": competition,
            "registration_open": registration_is_open(competition),
        },
    )
