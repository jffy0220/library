from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .analytics_config import ANALYTICS_ENABLED, ANALYTICS_IP_SALT
from .analytics_queue import insert_events


router = APIRouter(prefix="/analytics", tags=["analytics"])


def _hash_ip(ip: Optional[str]) -> Optional[str]:
    if not ip or not ANALYTICS_IP_SALT:
        return None
    material = (ip + ANALYTICS_IP_SALT).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: str
    ts: Optional[datetime] = None
    user_id: Optional[str] = None
    anonymous_id: str
    session_id: str
    route: Optional[str] = None
    duration_ms: Optional[int] = Field(default=None, ge=0)
    props: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _ensure_event_name(self) -> "Event":
        if not self.event or not self.event.strip():
            raise ValueError("event must be a non-empty string")
        self.event = self.event.strip()
        return self


class Batch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: List[Event]


@router.post("/collect")
async def collect(batch: Batch, request: Request) -> Dict[str, Any]:
    if not ANALYTICS_ENABLED:
        return {"ok": True, "n": 0}

    pool = getattr(request.app.state, "analytics_pool", None)
    if pool is None:
        return {"ok": True, "n": 0}

    if not batch.events:
        return {"ok": True, "n": 0}

    client_ip = request.client.host if request.client else None
    ip_hash = _hash_ip(client_ip)
    user_agent = request.headers.get("user-agent")
    now = datetime.now(timezone.utc)

    serialized = []
    for event in batch.events:
        payload = event.model_dump()
        payload.setdefault("props", {})
        payload.setdefault("context", {})
        payload.setdefault("duration_ms", None)
        payload["ip_hash"] = ip_hash
        payload["user_agent"] = user_agent
        payload["ts"] = event.ts or now
        serialized.append(payload)

    try:
        inserted = await insert_events(pool, serialized)
    except Exception as exc:  # pragma: no cover - defensive path
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR) from exc

    return {"ok": True, "n": inserted}
