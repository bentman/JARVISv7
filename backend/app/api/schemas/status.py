from __future__ import annotations

from pydantic import BaseModel

class WakeStatusResponse(BaseModel):
    provider: str
    available: bool
    reason: str