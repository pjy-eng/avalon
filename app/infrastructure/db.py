from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, create_engine, func
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


class EventRecord(Base):
    __tablename__ = "game_events"

    record_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    room_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    inserted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class RoomRecord(Base):
    __tablename__ = "rooms"

    room_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    ruleset: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ParticipantRecord(Base):
    __tablename__ = "room_participants"

    participant_id: Mapped[str] = mapped_column(String(160), primary_key=True)
    room_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    player_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    nickname: Mapped[str] = mapped_column(String(128), nullable=False)
    seat: Mapped[int] = mapped_column(Integer, nullable=False)
    participant_type: Mapped[str] = mapped_column(String(32), nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


class GameRecord(Base):
    __tablename__ = "room_games"

    room_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    phase: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


def make_engine(database_url: str) -> Engine:
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return create_engine(database_url, future=True)


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
