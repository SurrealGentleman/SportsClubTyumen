from typing import Any

from pwdlib.exceptions import PwdlibError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from sqladmin.authentication import AuthenticationBackend
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import Request

from app.admin.csrf import AdminCSRFMiddleware
from app.admin.rate_limit import LoginRateLimiter
from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.models import Admin


class AdminAuthentication(AuthenticationBackend):
    def __init__(
        self,
        *,
        secret_key: str,
        session_maker: sessionmaker[Session],
        https_only: bool,
    ) -> None:
        super().__init__(
            secret_key=secret_key,
            same_site="lax",
            https_only=https_only,
            max_age=8 * 60 * 60,
        )
        self.session_maker = session_maker
        self.middlewares.append(Middleware(AdminCSRFMiddleware))
        self.limiter = LoginRateLimiter(
            session_maker,
            secret_key,
            account_limit=settings.admin_login_account_limit,
            ip_limit=settings.admin_login_ip_limit,
            window_seconds=settings.admin_login_window_seconds,
        )
        self._dummy_password_hash = get_password_hash("not-the-admin-password")

    async def login(self, request: Request) -> bool:
        form = await request.form()
        login = str(form.get("username", "")).strip()
        password = str(form.get("password", ""))

        retry_after = await run_in_threadpool(
            self.limiter.consume,
            login,
            request.client.host if request.client else "unknown",
        )
        if retry_after:
            raise HTTPException(
                status_code=429,
                detail="Слишком много попыток входа. Повторите через "
                f"{retry_after} сек.",
                headers={"Retry-After": str(retry_after)},
            )

        admin_id = await run_in_threadpool(self._verify_credentials, login, password)
        if admin_id is None:
            return False

        request.session.clear()
        request.session["user_id"] = admin_id
        return True

    def _verify_credentials(self, login: str, password: str) -> int | None:
        with self.session_maker() as session:
            admin = session.execute(
                select(Admin.id, Admin.password_hash).where(
                    Admin.login == login,
                    Admin.is_active.is_(True),
                )
            ).first()

        password_hash = admin.password_hash if admin else self._dummy_password_hash
        try:
            password_is_valid = verify_password(password, password_hash)
        except PwdlibError:
            password_is_valid = False

        if admin is None or not password_is_valid:
            return None
        return admin.id

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return False

    async def authenticate(self, request: Request) -> bool:
        admin_id: Any = request.session.get("user_id")
        if not isinstance(admin_id, int):
            return False

        return await run_in_threadpool(self._is_active_admin, admin_id)

    def _is_active_admin(self, admin_id: int) -> bool:
        with self.session_maker() as session:
            admin = session.scalar(
                select(Admin.id).where(
                    Admin.id == admin_id,
                    Admin.is_active.is_(True),
                )
            )

        return admin is not None
