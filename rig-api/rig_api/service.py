"""Business rules for reservations and quarantine – shared by the API routes and background jobs."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import metrics
from .config import settings
from .models import Reservation, Rig, utcnow


class RigUnavailable(Exception):
    """Raised when a rig cannot be reserved (busy, quarantined, unknown)."""


def get_rig(db: Session, rig_id: str) -> Rig | None:
    return db.get(Rig, rig_id)


def active_reservation(db: Session, rig_id: str) -> Reservation | None:
    stmt = select(Reservation).where(Reservation.rig_id == rig_id, Reservation.released_at.is_(None))
    return db.scalars(stmt).first()


def reserve(db: Session, rig: Rig, owner: str, ttl_s: int | None = None) -> Reservation:
    if rig.quarantined:
        metrics.reservation_conflicts_total.labels(rig.id, rig.lab).inc()
        raise RigUnavailable(f"{rig.id} is quarantined: {rig.quarantine_reason}")
    if rig.state in ("FAILING", "UNREACHABLE"):
        metrics.reservation_conflicts_total.labels(rig.id, rig.lab).inc()
        raise RigUnavailable(f"{rig.id} is {rig.state}")
    if active_reservation(db, rig.id) is not None:
        metrics.reservation_conflicts_total.labels(rig.id, rig.lab).inc()
        raise RigUnavailable(f"{rig.id} is already reserved")
    res = Reservation(rig_id=rig.id, owner=owner, ttl_s=ttl_s or settings.reservation_default_ttl_s)
    db.add(res)
    db.flush()
    metrics.reservations_total.labels(rig.id, rig.lab).inc()
    return res


def reserve_any(db: Session, owner: str, lab: str | None, ttl_s: int | None = None) -> Reservation:
    """Pick the first free, healthy rig – optionally restricted to one lab."""
    stmt = select(Rig).where(Rig.quarantined.is_(False)).order_by(Rig.id)
    if lab:
        stmt = stmt.where(Rig.lab == lab)
    for rig in db.scalars(stmt):
        if rig.state != "IDLE":
            continue
        if active_reservation(db, rig.id) is not None:
            continue
        return reserve(db, rig, owner, ttl_s)
    raise RigUnavailable(f"no free rig available{' in lab ' + lab if lab else ''}")


def release(db: Session, rig: Rig, owner: str | None = None, reason: str = "released") -> Reservation | None:
    res = active_reservation(db, rig.id)
    if res is None:
        return None
    if owner and res.owner != owner:
        raise RigUnavailable(f"{rig.id} is reserved by {res.owner}, not {owner}")
    res.released_at = utcnow()
    res.release_reason = reason
    db.flush()
    return res


def quarantine(db: Session, rig: Rig, reason: str) -> None:
    if not rig.quarantined:
        metrics.quarantines_total.labels(rig.id, rig.lab).inc()
    rig.quarantined = True
    rig.quarantine_reason = reason
    # A quarantined rig must not stay locked by a job either.
    release(db, rig, reason="quarantined")
    db.flush()


def unquarantine(db: Session, rig: Rig) -> None:
    rig.quarantined = False
    rig.quarantine_reason = ""
    rig.failure_streak = 0
    db.flush()


def expired_reservations(db: Session) -> list[Reservation]:
    now = utcnow()
    stmt = select(Reservation).where(Reservation.released_at.is_(None))
    return [r for r in db.scalars(stmt) if r.reserved_at + timedelta(seconds=r.ttl_s) < now]


def reservation_age_s(res: Reservation | None) -> float | None:
    if res is None:
        return None
    return (utcnow() - res.reserved_at).total_seconds()
