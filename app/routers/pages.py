from datetime import UTC, date, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload
from starlette.datastructures import FormData
from starlette.templating import Jinja2Templates

from app.api.deps import SessionDep
from app.core.config import settings
from app.core.time import local_datetime
from app.models import Competition, RegistrationType, Sport
from app.models.training import WEEKDAY_NAMES
from app.schemas import IndividualRegistrationCreate, TeamRegistrationCreate
from app.services import registrations as registration_service

router = APIRouter(include_in_schema=False)
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

MONTH_NAMES = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


def format_date(value: date | datetime) -> str:
    if isinstance(value, datetime):
        value = local_datetime(value)
    return f"{value.day} {MONTH_NAMES[value.month]} {value.year}"


def format_datetime(value: datetime) -> str:
    value = local_datetime(value)
    return f"{format_date(value)}, {value:%H:%M}"


def registration_is_open(competition: Competition) -> bool:
    deadline = competition.registration_deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=UTC)
    return competition.is_registration_open and datetime.now(UTC) <= deadline


def get_published_competition(db: Session, slug: str) -> Competition:
    competition = db.scalar(
        select(Competition).where(
            Competition.slug == slug,
            Competition.is_published.is_(True),
        )
    )
    if competition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return competition


def registration_validation_errors(exc: ValidationError) -> dict[str, str]:
    errors: dict[str, str] = {}
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "form"
        error_type = str(error["type"])
        message = str(error["msg"])
        if "университетскую почту" in message:
            errors[field] = message.removeprefix("Value error, ")
        elif "не должны повторяться" in message:
            errors["form"] = message.removeprefix("Value error, ")
        elif error_type == "missing":
            errors[field] = "Заполните обязательное поле"
        elif field.endswith("email"):
            errors[field] = "Укажите корректный адрес университетской почты"
        elif field.endswith("course"):
            errors[field] = "Укажите курс от 1 до 6"
        else:
            errors[field] = "Проверьте значение поля"
    return errors


def parse_team_form(form: FormData) -> dict[str, object]:
    member_fields = {
        "full_name": [str(value) for value in form.getlist("member_full_name")],
        "university_email": [
            str(value) for value in form.getlist("member_university_email")
        ],
        "institute": [str(value) for value in form.getlist("member_institute")],
        "course": [str(value) for value in form.getlist("member_course")],
        "group_name": [str(value) for value in form.getlist("member_group_name")],
    }
    member_count = max((len(values) for values in member_fields.values()), default=0)
    members = [
        {
            field: values[index] if index < len(values) else ""
            for field, values in member_fields.items()
        }
        for index in range(member_count)
    ]
    return {
        "team_name": str(form.get("team_name", "")),
        "captain_name": str(form.get("captain_name", "")),
        "captain_email": str(form.get("captain_email", "")),
        "captain_phone": str(form.get("captain_phone", "")),
        "captain_institute": str(form.get("captain_institute", "")),
        "captain_course": str(form.get("captain_course", "")),
        "captain_group_name": str(form.get("captain_group_name", "")),
        "members": members,
    }


def registration_form_context(
    competition: Competition,
    *,
    form_data: dict[str, object] | None = None,
    errors: dict[str, str] | None = None,
    form_error: str | None = None,
) -> dict[str, object]:
    return {
        "competition": competition,
        "email_domain": settings.university_email_domain,
        "form_data": form_data or {},
        "errors": errors or {},
        "form_error": form_error,
        "initial_member_count": max((competition.min_team_size or 1) - 1, 0),
    }


templates.env.filters["date_ru"] = format_date
templates.env.filters["datetime_ru"] = format_datetime
templates.env.globals["weekday_names"] = WEEKDAY_NAMES


@router.get("/", response_class=HTMLResponse, name="home")
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")


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


@router.get(
    "/competitions/{slug}/register",
    response_class=HTMLResponse,
    name="register_for_competition",
)
def register_for_competition(
    slug: str,
    request: Request,
    db: SessionDep,
) -> HTMLResponse:
    competition = get_published_competition(db, slug)
    form_error = None
    try:
        registration_service.ensure_registration_available(competition)
    except registration_service.RegistrationError as exc:
        form_error = exc.message

    template_name = (
        "register_team.html"
        if competition.registration_type == RegistrationType.team
        else "register_individual.html"
    )
    return templates.TemplateResponse(
        request,
        template_name,
        registration_form_context(competition, form_error=form_error),
        status_code=(status.HTTP_409_CONFLICT if form_error else status.HTTP_200_OK),
    )


@router.post(
    "/competitions/{slug}/register",
    response_class=HTMLResponse,
)
async def submit_registration(
    slug: str,
    request: Request,
    db: SessionDep,
) -> HTMLResponse:
    competition = get_published_competition(db, slug)
    form = await request.form()
    is_team = competition.registration_type == RegistrationType.team
    form_data: dict[str, object] = (
        parse_team_form(form)
        if is_team
        else {key: str(value) for key, value in form.items()}
    )
    schema = TeamRegistrationCreate if is_team else IndividualRegistrationCreate
    template_name = "register_team.html" if is_team else "register_individual.html"
    try:
        registration_in = schema.model_validate(form_data)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request,
            template_name,
            registration_form_context(
                competition,
                form_data=form_data,
                errors=registration_validation_errors(exc),
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )

    try:
        if isinstance(registration_in, TeamRegistrationCreate):
            registration = registration_service.create_team_registration(
                db,
                competition=competition,
                registration_in=registration_in,
            )
        else:
            registration = registration_service.create_individual_registration(
                db,
                competition=competition,
                registration_in=registration_in,
            )
    except registration_service.RegistrationError as exc:
        return templates.TemplateResponse(
            request,
            template_name,
            registration_form_context(
                competition,
                form_data=form_data,
                form_error=exc.message,
            ),
            status_code=status.HTTP_409_CONFLICT,
        )

    return templates.TemplateResponse(
        request,
        "registration_success.html",
        {"competition": competition, "registration": registration},
        status_code=status.HTTP_201_CREATED,
    )
