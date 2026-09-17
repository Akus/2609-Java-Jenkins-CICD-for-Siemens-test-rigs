"""Background poller: asks every rig for /status, persists it, quarantines repeat offenders."""

import logging
import threading

import httpx
from sqlalchemy import select

from . import metrics, service
from .config import settings
from .db import session_scope
from .models import Rig, StatusHistory, utcnow

log = logging.getLogger("rig_api.poller")


def fetch_status(rig: Rig, client: httpx.Client) -> dict | None:
    """One HTTP round trip. Returns the JSON dict or None if unreachable/invalid."""
    metrics.polls_total.labels(rig.id, rig.lab).inc()
    try:
        r = client.get(f"http://{rig.host}:{rig.port}/status")
        r.raise_for_status()
        return r.json()
    except (httpx.HTTPError, ValueError) as e:
        metrics.poll_errors_total.labels(rig.id, rig.lab).inc()
        log.warning("poll %s failed: %s", rig.id, e)
        return None


def apply_status(db, rig: Rig, status: dict | None) -> None:
    """Update the row from one poll result. Pure DB logic – unit-testable without HTTP."""
    previous_state = rig.state
    if status is None:
        rig.state = "UNREACHABLE"
        rig.failure_streak += 1
        rig.last_error = "status poll failed"
    else:
        rig.state = str(status.get("state", "UNKNOWN"))
        rig.firmware = str(status.get("firmware", rig.firmware))
        rig.temperature_c = status.get("temperature_c")
        rig.last_seen = utcnow()
        rig.last_error = str(status.get("last_error", ""))
        if rig.state == "FAILING":
            rig.failure_streak += 1
        else:
            rig.failure_streak = 0

    if rig.state != previous_state:
        db.add(StatusHistory(rig_id=rig.id, state=rig.state, firmware=rig.firmware))
        log.info("%s: %s -> %s (fw=%s)", rig.id, previous_state, rig.state, rig.firmware)

    if rig.failure_streak >= settings.quarantine_after_failures and not rig.quarantined:
        reason = f"auto: {rig.failure_streak} consecutive failures ({rig.last_error})"
        log.error("quarantining %s – %s", rig.id, reason)
        service.quarantine(db, rig, reason)

    res = service.active_reservation(db, rig.id)
    metrics.publish_rig(rig, reserved=res is not None, reservation_age_s=service.reservation_age_s(res))


def poll_once(client: httpx.Client) -> None:
    with session_scope() as db:
        for rig in db.scalars(select(Rig)):
            apply_status(db, rig, fetch_status(rig, client))


class Poller(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="rig-poller", daemon=True)
        self._stop = threading.Event()

    def run(self) -> None:
        log.info("poller started (interval=%ss)", settings.poll_interval_s)
        with httpx.Client(timeout=settings.poll_timeout_s) as client:
            while not self._stop.is_set():
                try:
                    poll_once(client)
                except Exception:  # never let the thread die
                    log.exception("poll cycle failed")
                self._stop.wait(settings.poll_interval_s)

    def stop(self) -> None:
        self._stop.set()
