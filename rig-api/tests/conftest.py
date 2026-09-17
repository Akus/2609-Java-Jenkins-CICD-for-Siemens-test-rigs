import os
from pathlib import Path

# Must be set before rig_api is imported: the engine is built from settings at import time.
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["BACKGROUND_TASKS"] = "false"
os.environ["RIGS_INVENTORY"] = str(Path(__file__).parent / "rigs.test.yaml")
os.environ["RESERVATION_DEFAULT_TTL_S"] = "60"
os.environ["QUARANTINE_AFTER_FAILURES"] = "3"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import delete  # noqa: E402

from rig_api.db import SessionLocal, engine  # noqa: E402
from rig_api.main import app  # noqa: E402
from rig_api.models import Base, Reservation, Rig, StatusHistory  # noqa: E402


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:  # triggers lifespan: create_all + inventory seed
        yield c


@pytest.fixture(autouse=True)
def clean_state(client):
    """Reset mutable state between tests but keep the seeded inventory."""
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        db.execute(delete(Reservation))
        db.execute(delete(StatusHistory))
        for rig in db.query(Rig):
            rig.state = "IDLE"
            rig.failure_streak = 0
            rig.quarantined = False
            rig.quarantine_reason = ""
        db.commit()
    yield


@pytest.fixture
def db():
    with SessionLocal() as s:
        yield s
