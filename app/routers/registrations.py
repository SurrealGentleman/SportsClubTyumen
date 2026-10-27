from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import FormData

from app.db.dependencies import SessionDep, SessionFactoryDep
from app.core.config import settings
from app.core.privacy import consent_document_hash
from app.core.templating import templates
from app.models import Competition, RegistrationType
from app.routers._competition_helpers import get_published_competition
from app.schemas import IndividualRegistrationCreate, TeamRegistrationCreate
from app.services import registrations as registration_service
from app.services.captcha import CaptchaError, verify_smartcaptcha

router = APIRouter(include_in_schema=False)


def registration_validation_errors(exc: ValidationError) -> dict[str, str]:
    errors: dict[str, str] = {}
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "form"
        error_type = str(error["type"])
        message = str(error["msg"])
        if field == "personal_data_consent":
            errors[field] = "Дайте согласие на обработку персональных данных"
        elif field == "members_consents_confirmed":
            errors[field] = "Подтвердите получение согласий всех участников команды"
        elif field == "consent_version":
            errors[field] = "Документ согласия изменился. Прочитайте актуальную версию."
        elif "университетскую почту" in message:
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
        "personal_data_consent": str(form.get("personal_data_consent", "")),
        "consent_version": str(form.get("consent_version", "")),
        "members_consents_confirmed": str(form.get("members_consents_confirmed", "")),
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
        "consent_version": consent_document_hash(),
        "is_team_registration": competition.registration_type == RegistrationType.team,
        "captcha_enabled": settings.captcha_enabled,
        "captcha_ready": settings.captcha_ready,
        "captcha_client_key": settings.smartcaptcha_client_key
        if settings.captcha_ready
        else "",
    }


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
    session_factory: SessionFactoryDep,
) -> HTMLResponse:
    competition = await run_in_threadpool(
        _load_registration_competition, session_factory, slug
    )
    form = await request.form()
    return await run_in_threadpool(
        _submit_registration, competition, request, form, session_factory
    )


def _load_registration_competition(
    session_factory: sessionmaker[Session], slug: str
) -> Competition:
    # Only loaded column values leave this worker; the Session is closed here.
    with session_factory() as db:
        return get_published_competition(db, slug)


def _submit_registration(
    competition: Competition,
    request: Request,
    form: FormData,
    session_factory: sessionmaker[Session],
) -> HTMLResponse:
    is_team = competition.registration_type == RegistrationType.team
    form_data: dict[str, object] = (
        parse_team_form(form)
        if is_team
        else {key: str(value) for key, value in form.items() if key != "smart-token"}
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

    tokens = form.getlist("smart-token")
    captcha_token = str(tokens[0]) if len(tokens) == 1 else ""
    try:
        # This whole function is already running in a worker. No DB connection
        # is held while waiting for the external CAPTCHA service.
        verify_smartcaptcha(captcha_token, request.url.netloc)
    except CaptchaError as exc:
        return templates.TemplateResponse(
            request,
            template_name,
            registration_form_context(
                competition,
                form_data=form_data,
                errors={"captcha": exc.message},
            ),
            status_code=exc.status_code,
        )

    try:
        with session_factory() as db:
            # Reload after CAPTCHA: publication and registration settings may
            # have changed while the external service was being checked.
            current_competition = get_published_competition(db, competition.slug)
            if isinstance(registration_in, TeamRegistrationCreate):
                registration = registration_service.create_team_registration(
                    db,
                    competition=current_competition,
                    registration_in=registration_in,
                )
            else:
                registration = registration_service.create_individual_registration(
                    db,
                    competition=current_competition,
                    registration_in=registration_in,
                )
            # Render inside the worker/session so template attribute access
            # cannot perform a lazy query on the event-loop thread.
            return templates.TemplateResponse(
                request,
                "registration_success.html",
                {"competition": current_competition, "registration": registration},
                status_code=status.HTTP_201_CREATED,
            )
    except registration_service.RegistrationError as exc:
        consent_changed = isinstance(exc, registration_service.ConsentChangedError)
        return templates.TemplateResponse(
            request,
            template_name,
            registration_form_context(
                competition,
                form_data=form_data,
                errors={"consent_version": exc.message} if consent_changed else None,
                form_error=None if consent_changed else exc.message,
            ),
            status_code=status.HTTP_409_CONFLICT,
        )
