from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    """Naive UTC – SQLite has no tz-aware column type, so we keep every timestamp naive-UTC to stay comparable."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Rig(Base):
    """One physical (here: simulated) test rig board."""

    __tablename__ = "rigs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    lab: Mapped[str] = mapped_column(String(32), index=True)
    host: Mapped[str] = mapped_column(String(255))
    port: Mapped[int] = mapped_column(Integer, default=8080)
    # Last state observed by the poller: IDLE / BUSY / FLASHING / FAILING / UNREACHABLE
    state: Mapped[str] = mapped_column(String(16), default="UNKNOWN", index=True)
    firmware: Mapped[str] = mapped_column(String(64), default="")
    temperature_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)
    last_error: Mapped[str] = mapped_column(String(512), default="")
    failure_streak: Mapped[int] = mapped_column(Integer, default=0)
    quarantined: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    quarantine_reason: Mapped[str] = mapped_column(String(512), default="")

    reservations: Mapped[list["Reservation"]] = relationship(back_populates="rig", cascade="all, delete-orphan")

    @property
    def active_reservation(self) -> "Reservation | None":
        return next((r for r in self.reservations if r.released_at is None), None)


class Reservation(Base):
    """A pipeline (or a human) holding a rig. released_at NULL == active."""

    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rig_id: Mapped[str] = mapped_column(ForeignKey("rigs.id", ondelete="CASCADE"), index=True)
    owner: Mapped[str] = mapped_column(String(128))  # e.g. "rig-hil-pipeline#42"
    reserved_at: Mapped[datetime] = mapped_column(DateTime(), default=utcnow)
    ttl_s: Mapped[int] = mapped_column(Integer)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True, index=True)
    release_reason: Mapped[str] = mapped_column(String(64), default="")  # "released" | "watchdog-expired"

    rig: Mapped[Rig] = relationship(back_populates="reservations")


class StatusHistory(Base):
    """Append-only log of state transitions; feeds uptime reports."""

    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rig_id: Mapped[str] = mapped_column(ForeignKey("rigs.id", ondelete="CASCADE"), index=True)
    state: Mapped[str] = mapped_column(String(16))
    firmware: Mapped[str] = mapped_column(String(64), default="")
    ts: Mapped[datetime] = mapped_column(DateTime(), default=utcnow, index=True)
