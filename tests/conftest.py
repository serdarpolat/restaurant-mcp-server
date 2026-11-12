import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from pos_api.db.database import get_session
from pos_api.db.seed import seed
from pos_api.main import app


@pytest.fixture(scope="session")
def template_db(tmp_path_factory) -> Path:
    """Seed a small database once; each test gets its own copy."""
    path = tmp_path_factory.mktemp("db") / "template.db"
    seed(reset=True, days=7, db_engine=create_engine(f"sqlite:///{path}"), verbose=False)
    return path


@pytest.fixture
def engine(template_db, tmp_path):
    path = tmp_path / "test.db"
    shutil.copy(template_db, path)
    eng = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    with Session(engine) as s:
        yield s


@pytest.fixture
def client(engine):
    def override():
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
