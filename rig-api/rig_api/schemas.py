from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ReservationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rig_id: str
    owner: str
    reserved_at: datetime
    ttl_s: int
    released_at: datetime | None
    release_reason: str


class RigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    lab: str
    host: str
    port: int
    state: str
    firmware: str
    temperature_c: float | None
    last_seen: datetime | None
    last_error: str
    failure_streak: int
    quarantined: bool
    quarantine_reason: str
    reserved_by: str | None = None


class RigLiveStatus(BaseModel):
    """DB view plus the rig's own /status payload (if reachable)."""

    rig: RigOut
    live: dict | None
    reachable: bool


class ReserveRequest(BaseModel):
    owner: str = Field(..., examples=["rig-hil-pipeline#42"])
    ttl_s: int | None = Field(None, ge=30, le=24 * 3600)


class ReleaseRequest(BaseModel):
    owner: str | None = None  # if given, must match the active reservation


class QuarantineRequest(BaseModel):
    reason: str = "manual"


class OkResponse(BaseModel):
    ok: bool = True
    detail: str = ""
