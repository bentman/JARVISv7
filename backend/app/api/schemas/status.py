from __future__ import annotations

from pydantic import BaseModel

class WakeStatusResponse(BaseModel):
    provider: str
    available: bool
    reason: str
    monitoring: bool = False
    last_detected: bool = False
    detection_count: int = 0
    last_error: str | None = None