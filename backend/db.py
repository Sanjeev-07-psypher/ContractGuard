"""SQLModel engine and sessions for the SQLite database (HLD 10.3)."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import Engine
from sqlmodel import Session, SQLModel, create_engine

from backend import tables  # noqa: F401  (registers the tables)


def make_engine(sqlite_path: Path) -> Engine:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{sqlite_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return engine


def session_scope(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session
