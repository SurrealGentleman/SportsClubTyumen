from fastapi.testclient import TestClient


def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_uses_project_name(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert response.json()["info"]["title"] == "Спортивный клуб ТюмГУ"


def test_health_route_name_and_schema_are_preserved(
    client: TestClient, test_app
) -> None:
    assert str(test_app.url_path_for("health_check")) == "/api/v1/health"
    operation = client.get("/openapi.json").json()["paths"]["/api/v1/health"]["get"]
    assert operation["tags"] == ["Health"]
    assert operation["operationId"] == "health_check_api_v1_health_get"


def test_unversioned_health_url_is_not_exposed(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 404
