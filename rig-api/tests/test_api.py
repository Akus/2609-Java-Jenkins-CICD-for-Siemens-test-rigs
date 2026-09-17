from datetime import timedelta

from rig_api import service
from rig_api.models import Reservation, Rig, utcnow
from rig_api.poller import apply_status
from rig_api.watchdog import release_expired


# ------------------------------------------------------------- inventory

def test_inventory_seeded(client):
    rigs = client.get("/rigs").json()
    assert [r["id"] for r in rigs] == ["rig-munich-01", "rig-vienna-01", "rig-vienna-02"]
    assert all(r["reserved_by"] is None for r in rigs)


def test_filter_by_lab(client):
    rigs = client.get("/rigs", params={"lab": "vienna"}).json()
    assert {r["lab"] for r in rigs} == {"vienna"}
    assert len(rigs) == 2


def test_unknown_rig_404(client):
    assert client.get("/rigs/rig-nowhere-99").status_code == 404


# ----------------------------------------------------------- reservations

def test_reserve_release_roundtrip(client):
    r = client.post("/rigs/rig-vienna-01/reserve", json={"owner": "job#1"})
    assert r.status_code == 201, r.text
    assert r.json()["ttl_s"] == 60  # default from env
    assert client.get("/rigs/rig-vienna-01").json()["reserved_by"] == "job#1"

    active = client.get("/reservations").json()
    assert len(active) == 1 and active[0]["owner"] == "job#1"

    r = client.post("/rigs/rig-vienna-01/release", json={"owner": "job#1"})
    assert r.status_code == 200 and r.json()["detail"] == "released"
    assert client.get("/rigs/rig-vienna-01").json()["reserved_by"] is None


def test_double_reserve_conflicts(client):
    assert client.post("/rigs/rig-vienna-01/reserve", json={"owner": "job#1"}).status_code == 201
    r = client.post("/rigs/rig-vienna-01/reserve", json={"owner": "job#2"})
    assert r.status_code == 409
    assert "already reserved" in r.json()["detail"]


def test_release_by_wrong_owner_rejected(client):
    client.post("/rigs/rig-vienna-01/reserve", json={"owner": "job#1"})
    r = client.post("/rigs/rig-vienna-01/release", json={"owner": "job#2"})
    assert r.status_code == 409


def test_release_is_idempotent(client):
    r = client.post("/rigs/rig-vienna-01/release")
    assert r.status_code == 200
    assert r.json()["detail"] == "no active reservation"


def test_reserve_any_picks_free_rig_in_lab(client):
    r1 = client.post("/rigs/reserve", params={"lab": "vienna"}, json={"owner": "a"})
    r2 = client.post("/rigs/reserve", params={"lab": "vienna"}, json={"owner": "b"})
    r3 = client.post("/rigs/reserve", params={"lab": "vienna"}, json={"owner": "c"})
    assert (r1.status_code, r2.status_code, r3.status_code) == (201, 201, 409)
    assert {r1.json()["rig_id"], r2.json()["rig_id"]} == {"rig-vienna-01", "rig-vienna-02"}


def test_cannot_reserve_failing_rig(client, db):
    rig = db.get(Rig, "rig-munich-01")
    rig.state = "FAILING"
    db.commit()
    r = client.post("/rigs/rig-munich-01/reserve", json={"owner": "x"})
    assert r.status_code == 409 and "FAILING" in r.json()["detail"]


# ------------------------------------------------------------- quarantine

def test_quarantine_blocks_reservation_and_releases_holder(client):
    client.post("/rigs/rig-vienna-02/reserve", json={"owner": "job#7"})
    r = client.post("/rigs/rig-vienna-02/quarantine", json={"reason": "smoke coming out"})
    assert r.status_code == 200
    rig = client.get("/rigs/rig-vienna-02").json()
    assert rig["quarantined"] is True and rig["reserved_by"] is None

    assert client.post("/rigs/rig-vienna-02/reserve", json={"owner": "job#8"}).status_code == 409

    assert client.delete("/rigs/rig-vienna-02/quarantine").status_code == 200
    assert client.get("/rigs/rig-vienna-02").json()["quarantined"] is False
    assert client.post("/rigs/rig-vienna-02/reserve", json={"owner": "job#8"}).status_code == 201


def test_poller_auto_quarantines_after_streak(client, db):
    rig = db.get(Rig, "rig-munich-01")
    for _ in range(2):
        apply_status(db, rig, {"state": "FAILING", "firmware": "1.0", "last_error": "boom"})
    db.commit()
    assert rig.failure_streak == 2 and rig.quarantined is False

    apply_status(db, rig, None)  # unreachable counts too
    db.commit()
    assert rig.failure_streak == 3
    assert rig.quarantined is True
    assert "auto" in rig.quarantine_reason


def test_poller_records_state_transitions(client, db):
    rig = db.get(Rig, "rig-vienna-01")
    apply_status(db, rig, {"state": "IDLE", "firmware": "1.0.0", "temperature_c": 39.5})
    apply_status(db, rig, {"state": "BUSY", "firmware": "1.0.0", "temperature_c": 47.1})
    apply_status(db, rig, {"state": "BUSY", "firmware": "1.0.0", "temperature_c": 47.3})
    db.commit()
    history = client.get("/rigs/rig-vienna-01").json()
    assert history["state"] == "BUSY" and history["firmware"] == "1.0.0"
    from rig_api.models import StatusHistory
    assert db.query(StatusHistory).filter_by(rig_id="rig-vienna-01").count() == 1  # only the IDLE->BUSY edge


# --------------------------------------------------------------- watchdog

def test_watchdog_force_releases_expired(client, db):
    rig = db.get(Rig, "rig-vienna-01")
    res = service.reserve(db, rig, "crashed-job", ttl_s=30)
    res.reserved_at = utcnow() - timedelta(seconds=120)
    db.commit()

    assert release_expired() == 1
    db.expire_all()
    stale = db.get(Reservation, res.id)
    assert stale.released_at is not None
    assert stale.release_reason == "watchdog-expired"
    assert client.post("/rigs/rig-vienna-01/reserve", json={"owner": "next"}).status_code == 201


def test_watchdog_leaves_fresh_reservations(client, db):
    client.post("/rigs/rig-vienna-01/reserve", json={"owner": "fresh"})
    assert release_expired() == 0


# ------------------------------------------------------------------ infra

def test_metrics_and_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    body = client.get("/metrics").text
    assert 'rig_api_rig_state{rig="rig-vienna-01",lab="vienna",state="IDLE"}' in body
