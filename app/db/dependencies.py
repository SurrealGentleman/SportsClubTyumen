from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker


def get_session_factory(request: Request) -> sessionmaker[Session]:
    """Return a factory, never a live Session, to asynchronous handlers."""
    return request.app.state.session_factory


SessionFactoryDep = Annotated[sessionmaker[Session], Depends(get_session_factory)]


def get_db(session_factory: SessionFactoryDep) -> Generator[Session, None, None]:
    db = session_factory()

    try:
        yield db
    finally:
        db.close()


SessionDep = Annotated[Session, Depends(get_db)]
