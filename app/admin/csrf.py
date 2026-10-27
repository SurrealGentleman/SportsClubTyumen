from contextvars import ContextVar
import secrets
from urllib.parse import urlsplit

from starlette.datastructures import MutableHeaders
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


_token: ContextVar[str] = ContextVar("admin_csrf_token")


def admin_csrf_token() -> str:
    """Available even inside Jinja macros imported without context."""
    return _token.get()


def _origin(url: str) -> tuple[str, str | None, int | None]:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Invalid origin")
    return (
        parsed.scheme,
        parsed.hostname.lower(),
        parsed.port
        if parsed.port is not None
        else (443 if parsed.scheme == "https" else 80),
    )


class AdminCSRFMiddleware:
    """All unsafe admin requests, including login and AJAX DELETE, fail closed."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        existing = request.session.get("csrf_token")
        if not isinstance(existing, str):
            existing = None
        current = existing or secrets.token_urlsafe(32)
        context = _token.set(current)
        request.session["csrf_token"] = current
        try:
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                valid_origin = request.headers.get("sec-fetch-site") != "cross-site"
                source = request.headers.get("origin") or request.headers.get("referer")
                if source:
                    try:
                        valid_origin &= _origin(source) == _origin(str(request.url))
                    except ValueError:
                        valid_origin = False
                submitted = request.headers.get("x-csrf-token")
                if submitted is None and valid_origin and existing:
                    # Buffer once and replay for SQLAdmin's own multipart/form parser.
                    chunks = []
                    size = 0
                    while True:
                        message = await receive()
                        if message["type"] == "http.disconnect":
                            return
                        chunk = message.get("body", b"")
                        size += len(chunk)
                        if size > 1024 * 1024:
                            await PlainTextResponse(
                                "Форма слишком большая.", status_code=413
                            )(scope, receive, send)
                            return
                        chunks.append(chunk)
                        if not message.get("more_body", False):
                            break
                    body = b"".join(chunks)

                    def replay() -> Receive:
                        consumed = False

                        async def read() -> Message:
                            nonlocal consumed
                            if consumed:
                                return await receive()
                            consumed = True
                            return {"type": "http.request", "body": body}

                        return read

                    try:
                        async with Request(scope, replay()).form() as form:
                            submitted = form.get("csrf_token")
                    except Exception:
                        submitted = None
                    downstream_receive = replay()
                else:
                    downstream_receive = receive
                if not (
                    valid_origin
                    and existing
                    and isinstance(submitted, str)
                    and submitted.isascii()
                    and secrets.compare_digest(existing, submitted)
                ):
                    await PlainTextResponse(
                        "Не удалось проверить безопасность формы. "
                        "Обновите страницу и повторите отправку.",
                        status_code=403,
                    )(scope, receive, send)
                    return
            else:
                downstream_receive = receive

            async def no_cache(message: Message) -> None:
                if message["type"] == "http.response.start":
                    MutableHeaders(scope=message)["cache-control"] = "no-store"
                await send(message)

            await self.app(scope, downstream_receive, no_cache)
        finally:
            _token.reset(context)
