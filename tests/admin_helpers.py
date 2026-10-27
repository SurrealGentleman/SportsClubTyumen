import re

from fastapi.testclient import TestClient


def admin_token(client: TestClient, path: str = "/admin/login") -> str:
    response = client.get(path)
    match = re.search(r'name="csrf-token" content="([^"]+)"', response.text)
    assert match, response.text
    return match[1]


def admin_login(client: TestClient, *, data: dict, follow_redirects: bool = True):
    token = admin_token(client)
    response = client.post(
        "/admin/login",
        data={**data, "csrf_token": token},
        follow_redirects=follow_redirects,
    )
    if response.status_code == 302 or (
        response.status_code == 200 and response.url.path == "/admin/"
    ):
        client.headers["X-CSRF-Token"] = admin_token(client, "/admin/")
    return response
