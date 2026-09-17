from prometheus_client import Counter, Gauge

STATES = ("IDLE", "BUSY", "FLASHING", "FAILING", "UNREACHABLE", "UNKNOWN")

rig_state = Gauge("rig_api_rig_state", "1 if the rig is in this state", ["rig", "lab", "state"])
rig_reserved = Gauge("rig_api_reserved", "1 if the rig currently has an active reservation", ["rig", "lab"])
rig_quarantined = Gauge("rig_api_quarantined", "1 if the rig is quarantined", ["rig", "lab"])
rig_failure_streak = Gauge("rig_api_failure_streak", "Consecutive failed polls / FAILING observations", ["rig", "lab"])
rig_temperature = Gauge("rig_api_rig_temperature_celsius", "Last temperature reported by the rig", ["rig", "lab"])
reservation_age = Gauge("rig_api_reservation_age_seconds", "Age of the active reservation", ["rig", "lab"])

poll_errors_total = Counter("rig_api_poll_errors_total", "Failed status polls", ["rig", "lab"])
polls_total = Counter("rig_api_polls_total", "Status polls attempted", ["rig", "lab"])
reservations_total = Counter("rig_api_reservations_total", "Reservations granted", ["rig", "lab"])
reservation_conflicts_total = Counter("rig_api_reservation_conflicts_total", "Reserve requests refused", ["rig", "lab"])
watchdog_releases_total = Counter("rig_api_watchdog_releases_total", "Reservations force-released", ["rig", "lab"])
quarantines_total = Counter("rig_api_quarantines_total", "Times a rig was put into quarantine", ["rig", "lab"])


def publish_rig(rig, reserved: bool, reservation_age_s: float | None) -> None:
    """Refresh all gauges for one rig row."""
    for s in STATES:
        rig_state.labels(rig.id, rig.lab, s).set(1 if rig.state == s else 0)
    rig_reserved.labels(rig.id, rig.lab).set(1 if reserved else 0)
    rig_quarantined.labels(rig.id, rig.lab).set(1 if rig.quarantined else 0)
    rig_failure_streak.labels(rig.id, rig.lab).set(rig.failure_streak)
    if rig.temperature_c is not None:
        rig_temperature.labels(rig.id, rig.lab).set(rig.temperature_c)
    reservation_age.labels(rig.id, rig.lab).set(reservation_age_s or 0)
