from __future__ import annotations

from pydantic import BaseModel

class WakeStatusResponse(BaseModel):
    provider: str
    available: bool
    reason: str
    active: bool = False
    enabled: bool = False
    monitoring: bool = False
    last_detected: str | None = None
    detection_count: int = 0
    last_error: str | None = None
    last_score: float | None = None
    threshold: float | None = None
