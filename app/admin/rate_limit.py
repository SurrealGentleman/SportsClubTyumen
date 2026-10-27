import hashlib
import hmac
import secrets
import time

from sqlalchemy import Table, case, delete
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session, sessionmaker

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
        counter_table: Table | None = None,
    ) -> None:
        self.session_maker = session_maker
        self.secret_key = secret_key.encode()
        self.account_limit = account_limit
        self.ip_limit = ip_limit
        self.window_seconds = window_seconds
        self.counter_table = (
            counter_table if counter_table is not None else LoginAttempt.__table__
        )

    def consume(self, login: str, ip: str) -> int:
        return self.consume_buckets(
            (
                ("ip", ip, self.ip_limit),
                ("account", login.casefold(), self.account_limit),
            )
        )

    def consume_buckets(self, buckets: tuple[tuple[str, str, int], ...]) -> int:
        """Atomically reserve attempts before hashing; return Retry-After seconds."""
        now = int(time.time())
        table = self.counter_table
        columns = table.c
        retry_after = 0
        with self.session_maker.begin() as session:
            dialect = session.get_bind().dialect.name
            insert = pg_insert if dialect == "postgresql" else sqlite_insert
            # Identical order in every transaction also prevents cross-bucket deadlocks.
            for kind, value, limit in buckets:
                key = hmac.new(
                    self.secret_key, f"{kind}:{value}".encode(), hashlib.sha256
                ).hexdigest()
                expired = columns.window_start <= now - self.window_seconds
                statement = insert(table).values(key=key, window_start=now, attempts=1)
                statement = statement.on_conflict_do_update(
                    index_elements=[columns.key],
                    set_={
                        "window_start": case(
                            (expired, now), else_=columns.window_start
                        ),
                        "attempts": case(
                            (expired, 1),
                            else_=case(
                                (
                                    columns.attempts < limit + 1,
                                    columns.attempts + 1,
                                ),
                                else_=columns.attempts,
                            ),
                        ),
                    },
                ).returning(columns.attempts, columns.window_start)
                attempts, started = session.execute(statement).one()
                if attempts > limit:
                    retry_after = max(retry_after, started + self.window_seconds - now)
                    # Do not allocate arbitrary account rows once this IP is blocked.
                    break
        if secrets.randbelow(100) == 0:
            # Never hold counter locks while cleaning other rows: concurrent
            # workers renewing expired windows could otherwise deadlock.
            with self.session_maker.begin() as session:
                session.execute(
                    delete(table).where(
                        columns.window_start <= now - self.window_seconds
                    )
                )
        return retry_after
