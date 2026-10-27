from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException
from starlette.responses import Response
from starlette.templating import Jinja2Templates

ERROR_MESSAGES = {
    403: (
        "Доступ ограничен",
        "У вас нет доступа к этой странице. Вы можете вернуться на главную страницу клуба.",
    ),
    404: (
        "Страница не найдена",
        "Возможно, ссылка устарела или в адресе есть опечатка. "
        "Расписание и соревнования доступны через меню сайта.",
    ),
    405: (
        "Действие недоступно",
        "Эта страница не поддерживает такое действие. "
        "Вернитесь на главную и воспользуйтесь навигацией сайта.",
    ),
    500: (
        "Не удалось загрузить страницу",
        "На сайте произошла ошибка. Попробуйте снова чуть позже.",
    ),
    503: (
        "Сайт временно недоступен",
        "Попробуйте зайти немного позже. Мы ждём вас на тренировках и соревнованиях.",
    ),
}


def wants_json_response(request: Request) -> bool:
    path = request.url.path
    accept = request.headers.get("accept", "").lower()
    return (
        path in {"/api", "/static", "/openapi.json"}
        or path.startswith(("/api/", "/static/"))
        or ("application/json" in accept and "text/html" not in accept)
    )


def setup_error_handlers(app: FastAPI, templates: Jinja2Templates) -> None:
    def render_error(
        request: Request,
        status_code: int,
        headers: dict[str, str] | None = None,
    ) -> Response:
        title, description = ERROR_MESSAGES.get(
            status_code,
            (
                "Не удалось открыть страницу",
                "Попробуйте вернуться на главную страницу клуба.",
            ),
        )
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "error_code": status_code,
                "error_title": title,
                "error_description": description,
            },
            status_code=status_code,
            headers=headers,
        )

    async def handle_http_error(request: Request, exc: HTTPException) -> Response:
        if wants_json_response(request):
            return await http_exception_handler(request, exc)
        return render_error(request, exc.status_code, exc.headers)

    async def handle_server_error(request: Request, exc: Exception) -> Response:
        if wants_json_response(request):
            return JSONResponse({"detail": "Internal Server Error"}, status_code=500)
        return render_error(request, 500)

    app.add_exception_handler(HTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_server_error)
