from fastapi import FastAPI, Request
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)
from starlette.responses import HTMLResponse


def setup_api_docs(app: FastAPI) -> None:
    def nonced(response: HTMLResponse, request: Request) -> HTMLResponse:
        # These are fixed, trusted FastAPI templates, never submitted HTML.
        body = response.body.decode().replace(
            "<script>", f'<script nonce="{request.state.csp_nonce}">'
        )
        return HTMLResponse(body)

    @app.get("/docs", include_in_schema=False)
    async def swagger(request: Request) -> HTMLResponse:
        root = request.scope.get("root_path", "").rstrip("/")
        return nonced(
            get_swagger_ui_html(
                openapi_url=f"{root}{app.openapi_url}",
                title=f"{app.title} - Swagger UI",
                oauth2_redirect_url=f"{root}/docs/oauth2-redirect",
            ),
            request,
        )

    @app.get("/docs/oauth2-redirect", include_in_schema=False)
    async def oauth_redirect(request: Request) -> HTMLResponse:
        return nonced(get_swagger_ui_oauth2_redirect_html(), request)

    @app.get("/redoc", include_in_schema=False)
    async def redoc(request: Request) -> HTMLResponse:
        root = request.scope.get("root_path", "").rstrip("/")
        return nonced(
            get_redoc_html(
                openapi_url=f"{root}{app.openapi_url}",
                title=f"{app.title} - ReDoc",
            ),
            request,
        )
