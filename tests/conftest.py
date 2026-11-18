import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, delete, select

from pos_api.db.database import get_session
from pos_api.db.models import DiningTable, Order, OrderItem, OrderStatus, Payment, TableStatus
from pos_api.db.seed import seed
from pos_api.main import app


@pytest.fixture(autouse=True)
def _confirmation_store(tmp_path, monkeypatch):
    """Keep pending confirmation tokens out of the real home folder."""
    monkeypatch.setenv("POS_MCP_STATE_DIR", str(tmp_path / "state"))


@pytest.fixture(scope="session")
def template_db(tmp_path_factory) -> Path:
    """Seed a small database once; each test gets its own copy."""
    path = tmp_path_factory.mktemp("db") / "template.db"
    engine = create_engine(f"sqlite:///{path}")
    seed(reset=True, days=7, db_engine=engine, verbose=False)
    # The seed leaves some tables mid-meal depending on the hour it runs; start every test
    # from an empty floor so results do not depend on the time of day.
    with Session(engine) as session:
        open_ids = session.exec(select(Order.id).where(Order.status == OrderStatus.open)).all()
        if open_ids:
            session.exec(delete(OrderItem).where(OrderItem.order_id.in_(open_ids)))
            session.exec(delete(Payment).where(Payment.order_id.in_(open_ids)))
            session.exec(delete(Order).where(Order.id.in_(open_ids)))
        for table in session.exec(select(DiningTable)).all():
            table.status = TableStatus.free
        session.commit()
    engine.dispose()
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
