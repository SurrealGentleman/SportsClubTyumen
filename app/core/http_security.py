from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.rate_limit import DatabaseRateLimiter


class RequestLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        limiter: DatabaseRateLimiter,
        request_limit: int,
        registration_limit: int,
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.request_limit = request_limit
        self.registration_limit = registration_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive)
        path = request.url.path
        if path == "/api/v1/health" or path.startswith(("/static/", "/admin/statics/")):
            await self.app(scope, receive, send)
            return
        ip = request.client.host if request.client else "unknown"
        buckets = (("web:ip", ip, self.request_limit),)
        if request.method == "POST" and path.startswith("/competitions/"):
            buckets += (("registration:ip", ip, self.registration_limit),)
        retry = await run_in_threadpool(self.limiter.consume_buckets, buckets)
        if retry:
            message = f"Слишком много запросов. Повторите через {retry} сек."
            headers = {"Retry-After": str(retry), "Cache-Control": "no-store"}
            if path.startswith("/api/") or "application/json" in request.headers.get(
                "accept", ""
            ):
                response = JSONResponse(
                    {"detail": message}, status_code=429, headers=headers
                )
            else:
                response = PlainTextResponse(message, status_code=429, headers=headers)
            await response(scope, receive, send)
            return
        await self.app(scope, receive, send)
