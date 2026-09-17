"""Seed / sync the rig inventory from rigs.yaml (the source of truth for what hardware exists)."""

import logging
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from .models import Rig

log = logging.getLogger("rig_api.inventory")


def load_inventory(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    rigs = data.get("rigs", [])
    for r in rigs:
        for key in ("id", "lab", "host"):
            if key not in r:
                raise ValueError(f"rig entry missing '{key}': {r}")
    return rigs


def sync_inventory(db: Session, rigs: list[dict]) -> int:
    """Upsert rows from the YAML. Never deletes – decommissioning is an explicit operator action."""
    changed = 0
    for entry in rigs:
        rig = db.get(Rig, entry["id"])
        if rig is None:
            rig = Rig(id=entry["id"], lab=entry["lab"], host=entry["host"], port=int(entry.get("port", 8080)))
            db.add(rig)
            log.info("registered new rig %s (%s @ %s:%s)", rig.id, rig.lab, rig.host, rig.port)
            changed += 1
        else:
            new_host, new_port = entry["host"], int(entry.get("port", 8080))
            if (rig.lab, rig.host, rig.port) != (entry["lab"], new_host, new_port):
                rig.lab, rig.host, rig.port = entry["lab"], new_host, new_port
                changed += 1
    db.flush()
    return changed
