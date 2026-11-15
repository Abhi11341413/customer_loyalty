"""SQLAlchemy engine and session factory.

Owner: M1. Minimal version written by M4 so the review/delivery/audit tables can be used;
M1 please review/extend.
"""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.data.models import Base
from config.settings import get_settings


def make_engine(url: str) -> Engine:
    """Create an engine with SQLite foreign keys enforced.

    In-memory URLs share one connection so tests see a single database.
    """
    kwargs: dict = {}
    if url in ("sqlite://", "sqlite:///:memory:"):
        kwargs = {"connect_args": {"check_same_thread": False}, "poolclass": StaticPool}
    elif url.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):  # pragma: no cover - trivial
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def create_all(engine: Engine) -> None:
    Base.metadata.create_all(engine)


@lru_cache
def default_engine() -> Engine:
    return make_engine(get_settings().database_url)


def session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=engine or default_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """FastAPI dependency. M4 can override it via app.dependency_overrides."""
    session = session_factory()()
    try:
        yield session
    finally:
        session.close()
