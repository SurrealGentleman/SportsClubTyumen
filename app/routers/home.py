from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.templating import templates

router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse, name="home")
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "index.html")
