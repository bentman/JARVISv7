from __future__ import annotations

from pydantic import BaseModel


class AgentsStatusResponse(BaseModel):
    enabled: bool
    read_only: bool
    reason: str