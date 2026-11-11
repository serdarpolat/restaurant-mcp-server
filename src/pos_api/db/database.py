"""Database engine and session helpers."""

import os
from collections.abc import Iterator
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from sqlmodel import Session, SQLModel, create_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./restaurant.db")
RESTAURANT_TZ = ZoneInfo(os.getenv("RESTAURANT_TZ", "Europe/Istanbul"))

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)


def create_db_and_tables() -> None:
    # Import models so they are registered on SQLModel.metadata
    from pos_api.db import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def drop_db_and_tables() -> None:
    from pos_api.db import models  # noqa: F401

    SQLModel.metadata.drop_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
