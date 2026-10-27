import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    "path",
    [
        "/missing-page",
        "/sports/missing-sport",
        "/competitions/missing-competition",
        "/competitions/missing-competition/register",
    ],
)
def test_missing_public_pages_render_html(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("text/html")
    assert "Страница не найдена" in response.text
    assert "На главную" in response.text
    assert "Соревнования" in response.text
    assert 'rel="icon"' in response.text


@pytest.mark.parametrize("path", ["/api", "/api/v1/missing", "/static/missing.png"])
def test_missing_service_resources_keep_json(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_explicit_json_request_keeps_json(client: TestClient) -> None:
    response = client.get("/missing-page", headers={"Accept": "application/json"})

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


def test_unsupported_method_keeps_status_and_allow_header(client: TestClient) -> None:
    response = client.post("/")

    assert response.status_code == 405
    assert response.headers["allow"] == "GET"
    assert "Действие недоступно" in response.text


@pytest.mark.parametrize(
    ("status_code", "title", "headers"),
    [
        (403, "Доступ ограничен", {}),
        (503, "Сайт временно недоступен", {"Retry-After": "60"}),
    ],
)
def test_http_errors_render_html_and_keep_headers(
    test_app: FastAPI,
    status_code: int,
    title: str,
    headers: dict[str, str],
) -> None:
    @test_app.get("/test-error")
    def fail() -> None:
        raise HTTPException(status_code, "private error details", headers=headers)

    with TestClient(test_app) as client:
        response = client.get("/test-error")

    assert response.status_code == status_code
    assert title in response.text
    assert "private error details" not in response.text
    for name, value in headers.items():
        assert response.headers[name] == value


@pytest.mark.parametrize("path", ["/test-error", "/api/v1/test-error"])
def test_production_server_errors_hide_internal_details(
    test_app: FastAPI, path: str
) -> None:
    test_app.debug = False

    @test_app.get(path)
    def fail() -> None:
        raise RuntimeError("private database error")

    with TestClient(test_app, raise_server_exceptions=False) as client:
        response = client.get(path)

    assert response.status_code == 500
    assert "private database error" not in response.text
    assert "Traceback" not in response.text
    if path.startswith("/api/"):
        assert response.json() == {"detail": "Internal Server Error"}
    else:
        assert response.headers["content-type"].startswith("text/html")
        assert "Не удалось загрузить страницу" in response.text
