"""Admin login policy built on the shared database rate limiter."""

from sqlalchemy.orm import Session, sessionmaker

from app.core.rate_limit import DatabaseRateLimiter
from app.models import LoginAttempt


class LoginRateLimiter:
    def __init__(
        self,
        session_maker: sessionmaker[Session],
        secret_key: str,
        *,
        account_limit: int,
        ip_limit: int,
        window_seconds: int,
    ) -> None:
        self.account_limit = account_limit
        self.ip_limit = ip_limit
        self._counter = DatabaseRateLimiter(
            session_maker,
            secret_key,
            window_seconds=window_seconds,
            counter_table=LoginAttempt.__table__,
        )

    def consume(self, login: str, ip: str) -> int:
        # Keep IP first: a blocked IP must not allocate arbitrary account rows.
        return self._counter.consume_buckets(
            (
                ("ip", ip, self.ip_limit),
                ("account", login.casefold(), self.account_limit),
            )
        )
