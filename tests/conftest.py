from collections.abc import Generator
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["APP_DEBUG"] = "true"
os.environ["APP_NAME"] = "Спортивный клуб ТюмГУ"
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["SESSION_COOKIE_SECURE"] = "false"
os.environ["UNIVERSITY_EMAIL_DOMAIN"] = "study.utmn.ru"

from app.api.deps import get_db
from app.db.base import Base
from app.main import create_app


@pytest.fixture()
def db_engine() -> Generator[Engine, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)

    yield engine

    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def testing_session_maker(db_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=db_engine,
        class_=Session,
        autoflush=False,
        expire_on_commit=False,
    )


@pytest.fixture()
def db_session(
    testing_session_maker: sessionmaker[Session],
) -> Generator[Session, None, None]:
    with testing_session_maker() as session:
        yield session


@pytest.fixture()
def test_app(
    db_engine: Engine,
    testing_session_maker: sessionmaker[Session],
) -> Generator[FastAPI, None, None]:
    app = create_app(
        db_engine=db_engine,
        session_maker=testing_session_maker,
    )

    def override_get_db() -> Generator[Session, None, None]:
        with testing_session_maker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    yield app
    app.dependency_overrides.clear()


@pytest.fixture()
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(test_app) as test_client:
        yield test_client
