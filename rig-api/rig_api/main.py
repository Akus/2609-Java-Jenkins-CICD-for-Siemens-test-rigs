"""Rig broker REST API.

    GET    /rigs                       inventory + live state
    GET    /rigs/{id}
    GET    /rigs/{id}/status           DB row + live proxy of the rig's own /status
    POST   /rigs/reserve?lab=vienna    reserve any free rig (optionally in one lab)
    POST   /rigs/{id}/reserve          reserve a specific rig (409 if not available)
    POST   /rigs/{id}/release
    POST   /rigs/{id}/quarantine
    DELETE /rigs/{id}/quarantine
    POST   /rigs/{id}/reset            proxy a remote reset to the rig
    GET    /reservations?active=true
    GET    /metrics                    Prometheus
    GET    /healthz
"""

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import inventory, metrics, service
from .config import settings
from .db import engine, get_db, session_scope
from .models import Base, Reservation, Rig
from .poller import Poller
from .schemas import (OkResponse, QuarantineRequest, ReleaseRequest, ReservationOut, ReserveRequest,
                      RigLiveStatus, RigOut)
from .watchdog import Watchdog

logging.basicConfig(level=settings.log_level.upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("rig_api")

_background: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Schema: Alembic migrations are the production path (`alembic upgrade head` in the entrypoint);
    # create_all keeps tests and ad-hoc runs self-contained.
    Base.metadata.create_all(engine)
    with session_scope() as db:
        rigs = inventory.load_inventory(settings.rigs_inventory)
        inventory.sync_inventory(db, rigs)
        for rig in db.scalars(select(Rig)):
            metrics.publish_rig(rig, reserved=False, reservation_age_s=None)
    if settings.background_tasks:
        for t in (Poller(), Watchdog()):
            t.start()
            _background.append(t)
    yield
    for t in _background:
        t.stop()


app = FastAPI(title="Rig Broker API", version="1.0.0", lifespan=lifespan)


# ------------------------------------------------------------------ helpers

def _rig_or_404(db: Session, rig_id: str) -> Rig:
    rig = service.get_rig(db, rig_id)
    if rig is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown rig {rig_id}")
    return rig


def _to_out(db: Session, rig: Rig) -> RigOut:
    out = RigOut.model_validate(rig)
    res = service.active_reservation(db, rig.id)
    out.reserved_by = res.owner if res else None
    return out


# --------------------------------------------------------------------- rigs

@app.get("/rigs", response_model=list[RigOut])
def list_rigs(lab: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Rig).order_by(Rig.id)
    if lab:
        stmt = stmt.where(Rig.lab == lab)
    return [_to_out(db, r) for r in db.scalars(stmt)]


# NOTE: declared before /rigs/{rig_id}/... so "reserve" is not captured as a rig id.
@app.post("/rigs/reserve", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def reserve_any(body: ReserveRequest, lab: str | None = Query(None), db: Session = Depends(get_db)):
    try:
        res = service.reserve_any(db, body.owner, lab, body.ttl_s)
    except service.RigUnavailable as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    db.commit()
    return res


@app.get("/rigs/{rig_id}", response_model=RigOut)
def get_rig(rig_id: str, db: Session = Depends(get_db)):
    return _to_out(db, _rig_or_404(db, rig_id))


@app.get("/rigs/{rig_id}/status", response_model=RigLiveStatus)
def rig_status(rig_id: str, db: Session = Depends(get_db)):
    rig = _rig_or_404(db, rig_id)
    live, reachable = None, False
    try:
        r = httpx.get(f"http://{rig.host}:{rig.port}/status", timeout=settings.poll_timeout_s)
        r.raise_for_status()
        live, reachable = r.json(), True
    except (httpx.HTTPError, ValueError):
        pass
    return RigLiveStatus(rig=_to_out(db, rig), live=live, reachable=reachable)


@app.post("/rigs/{rig_id}/reserve", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def reserve_rig(rig_id: str, body: ReserveRequest, db: Session = Depends(get_db)):
    rig = _rig_or_404(db, rig_id)
    try:
        res = service.reserve(db, rig, body.owner, body.ttl_s)
    except service.RigUnavailable as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    db.commit()
    return res


@app.post("/rigs/{rig_id}/release", response_model=OkResponse)
def release_rig(rig_id: str, body: ReleaseRequest | None = None, db: Session = Depends(get_db)):
    rig = _rig_or_404(db, rig_id)
    try:
        res = service.release(db, rig, body.owner if body else None)
    except service.RigUnavailable as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    db.commit()
    # Idempotent: releasing an unreserved rig is fine – post{always} in Jenkins relies on that.
    return OkResponse(detail="released" if res else "no active reservation")


@app.post("/rigs/{rig_id}/quarantine", response_model=OkResponse)
def quarantine_rig(rig_id: str, body: QuarantineRequest, db: Session = Depends(get_db)):
    rig = _rig_or_404(db, rig_id)
    service.quarantine(db, rig, body.reason)
    db.commit()
    return OkResponse(detail=f"{rig_id} quarantined")


@app.delete("/rigs/{rig_id}/quarantine", response_model=OkResponse)
def unquarantine_rig(rig_id: str, db: Session = Depends(get_db)):
    rig = _rig_or_404(db, rig_id)
    service.unquarantine(db, rig)
    db.commit()
    return OkResponse(detail=f"{rig_id} back in service")


@app.post("/rigs/{rig_id}/reset", response_model=OkResponse)
def reset_rig(rig_id: str, db: Session = Depends(get_db)):
    """Remote reset – what the 2am on-call does before escalating to on-site staff."""
    rig = _rig_or_404(db, rig_id)
    try:
        r = httpx.post(f"http://{rig.host}:{rig.port}/reset", timeout=settings.poll_timeout_s)
        r.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"rig did not accept reset: {e}")
    rig.failure_streak = 0
    db.commit()
    return OkResponse(detail=f"{rig_id} reset")


# ------------------------------------------------------------- reservations

@app.get("/reservations", response_model=list[ReservationOut])
def list_reservations(active: bool = Query(True), limit: int = Query(100, le=1000), db: Session = Depends(get_db)):
    stmt = select(Reservation).order_by(Reservation.reserved_at.desc()).limit(limit)
    if active:
        stmt = stmt.where(Reservation.released_at.is_(None))
    return list(db.scalars(stmt))


# ------------------------------------------------------------------- infra

@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics_endpoint():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
