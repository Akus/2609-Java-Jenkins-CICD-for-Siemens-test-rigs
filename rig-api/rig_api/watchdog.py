"""Watchdog: force-release reservations whose TTL expired (crashed job, lost agent, ...)."""

import logging
import threading

from . import metrics, service
from .config import settings
from .db import session_scope

log = logging.getLogger("rig_api.watchdog")


def release_expired() -> int:
    """Returns the number of reservations released. Safe to call from tests."""
    released = 0
    with session_scope() as db:
        for res in service.expired_reservations(db):
            log.warning("reservation %s on %s by %s exceeded ttl=%ss – force releasing",
                        res.id, res.rig_id, res.owner, res.ttl_s)
            service.release(db, res.rig, reason="watchdog-expired")
            metrics.watchdog_releases_total.labels(res.rig.id, res.rig.lab).inc()
            released += 1
    return released


class Watchdog(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name="rig-watchdog", daemon=True)
        self._stop = threading.Event()

    def run(self) -> None:
        log.info("watchdog started (interval=%ss)", settings.watchdog_interval_s)
        while not self._stop.is_set():
            try:
                release_expired()
            except Exception:
                log.exception("watchdog cycle failed")
            self._stop.wait(settings.watchdog_interval_s)

    def stop(self) -> None:
        self._stop.set()
