from fastapi import APIRouter, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from app.core.templating import templates

router = APIRouter(include_in_schema=False)


@router.get(
    "/legal/personal-data-consent",
    response_class=HTMLResponse,
    name="personal_data_consent",
)
def personal_data_consent(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "legal/personal_data_consent.html")


@router.get(
    "/legal/personal-data-consent/download",
    response_class=HTMLResponse,
    name="download_personal_data_consent",
)
def download_personal_data_consent(request: Request) -> RedirectResponse:
    return RedirectResponse(
        request.url_for("personal_data_consent"), status_code=status.HTTP_303_SEE_OTHER
    )


@router.get(
    "/legal/privacy-policy",
    response_class=HTMLResponse,
    name="privacy_policy",
)
def privacy_policy(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "legal/privacy_policy.html")
