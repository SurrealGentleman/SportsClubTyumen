"""Contracts of the shared counter and the separate admin login policy."""

import hashlib
import hmac

from sqlalchemy import select

from app.admin.rate_limit import LoginRateLimiter
from app.core.rate_limit import DatabaseRateLimiter
from app.models import LoginAttempt, RequestLimit


def counter(sessions):
    return DatabaseRateLimiter(
        sessions,
        "test-secret",
        window_seconds=60,
        counter_table=RequestLimit.__table__,
    )


def test_generic_counter_preserves_fixed_window_and_saturates(
    testing_session_maker,
    monkeypatch,
):
    now = [10000]
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: now[0])
    limiter = counter(testing_session_maker)
    buckets = (("web:ip", "192.0.2.1", 3),)
    assert [limiter.consume_buckets(buckets) for _ in range(4)] == [0, 0, 0, 60]
    now[0] = 10059
    assert limiter.consume_buckets(buckets) == 1
    with testing_session_maker() as session:
        row = session.scalar(select(RequestLimit))
        assert row.attempts == 4
        assert row.window_start == 10000
    now[0] = 10060
    assert limiter.consume_buckets(buckets) == 0
    with testing_session_maker() as session:
        row = session.scalar(select(RequestLimit))
        assert row.attempts == 1
        assert row.window_start == 10060


def test_generic_counter_stops_at_first_exhausted_bucket(testing_session_maker):
    limiter = counter(testing_session_maker)
    first = ("web:ip", "192.0.2.1", 1)
    assert limiter.consume_buckets((first,)) == 0
    assert limiter.consume_buckets((first, ("registration:ip", "192.0.2.1", 10))) > 0
    with testing_session_maker() as session:
        assert len(session.scalars(select(RequestLimit)).all()) == 1
        assert session.scalar(select(LoginAttempt)) is None


def test_login_policy_recognizes_existing_account_counter(
    testing_session_maker,
    monkeypatch,
):
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: 10010)
    # Same key format and table as before extracting DatabaseRateLimiter.
    old_key = hmac.new(b"test-secret", b"account:admin", hashlib.sha256).hexdigest()
    with testing_session_maker.begin() as session:
        session.add(LoginAttempt(key=old_key, window_start=10000, attempts=5))
    limiter = LoginRateLimiter(
        testing_session_maker,
        "test-secret",
        account_limit=5,
        ip_limit=30,
        window_seconds=900,
    )
    assert limiter.consume("ADMIN", "192.0.2.1") == 890
    with testing_session_maker() as session:
        assert session.get(LoginAttempt, old_key).attempts == 6
        assert session.scalar(select(RequestLimit)) is None


def test_login_policy_checks_ip_before_allocating_account(testing_session_maker):
    limiter = LoginRateLimiter(
        testing_session_maker,
        "test-secret",
        account_limit=5,
        ip_limit=1,
        window_seconds=900,
    )
    assert limiter.consume("first", "192.0.2.1") == 0
    assert limiter.consume("second", "192.0.2.1") > 0
    with testing_session_maker() as session:
        assert len(session.scalars(select(LoginAttempt)).all()) == 2
