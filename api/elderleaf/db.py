"""Database models. SQLite locally; Supabase Postgres in production (set DATABASE_URL)."""

from __future__ import annotations

import secrets
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

from .config import settings


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(5)}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Plot(Base):
    __tablename__ = "plots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("p"))
    device_id: Mapped[str | None] = mapped_column(String(64), index=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False)
    name: Mapped[str] = mapped_column(String(120))
    crop: Mapped[str] = mapped_column(String(40))
    planted_on: Mapped[date | None] = mapped_column(Date)
    area_m2: Mapped[float | None] = mapped_column(Float)
    row_spacing_cm: Mapped[float | None] = mapped_column(Float)
    plant_spacing_cm: Mapped[float | None] = mapped_column(Float)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    analyses: Mapped[list[Analysis]] = relationship(back_populates="plot", cascade="all, delete-orphan")
    notes: Mapped[list[Note]] = relationship(back_populates="plot", cascade="all, delete-orphan")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("a"))
    plot_id: Mapped[str] = mapped_column(ForeignKey("plots.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(16), default="photo")
    captured_at: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|running|done|failed
    image_key: Mapped[str] = mapped_column(String(255))
    image_width: Mapped[int | None] = mapped_column(Integer)
    image_height: Mapped[int | None] = mapped_column(Integer)
    trace: Mapped[list] = mapped_column(JSON, default=list)
    result: Mapped[dict | None] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)

    plot: Mapped[Plot] = relationship(back_populates="analyses")


class Note(Base):
    __tablename__ = "notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: new_id("n"))
    plot_id: Mapped[str] = mapped_column(ForeignKey("plots.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    noted_on: Mapped[date] = mapped_column(Date)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    plot: Mapped[Plot] = relationship(back_populates="notes")


def _database_url(url: str) -> str:
    # Supabase hands out postgres:// URLs; we ship psycopg 3
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def _make_engine():
    url = _database_url(settings.database_url)
    kwargs: dict = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        path = url.split("///", 1)[-1]
        if path and path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(url, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(engine)


def get_db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session
