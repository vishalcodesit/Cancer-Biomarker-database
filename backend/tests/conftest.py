"""Test fixtures: an isolated in-memory SQLite database loaded with the curated sample data."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.config import BACKEND_DIR
from app.database import Base, get_db, make_engine
from app.main import app
from app.services.importer import import_directory
from app.services.scores import recompute_all
from app.views import create_views

SAMPLE_DIR = BACKEND_DIR / "data" / "sample"


def _engine():
    from sqlalchemy import create_engine, event

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def _fk(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        create_views(conn)
    return engine


@pytest.fixture
def empty_db():
    engine = _engine()
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture(scope="session")
def loaded_engine():
    engine = _engine()
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as s:
        reports = import_directory(s, SAMPLE_DIR)
        assert all(r.ok for r in reports), [r.errors for r in reports if not r.ok]
        recompute_all(s)
    return engine


@pytest.fixture
def db(loaded_engine):
    Session = sessionmaker(bind=loaded_engine, autoflush=False, expire_on_commit=False)
    with Session() as s:
        yield s


@pytest.fixture
def client(loaded_engine):
    Session = sessionmaker(bind=loaded_engine, autoflush=False, expire_on_commit=False)

    def _get_db():
        with Session() as s:
            yield s

    app.dependency_overrides[get_db] = _get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


__all__ = ["make_engine"]
