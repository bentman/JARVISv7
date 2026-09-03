from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DaemonStatusResponse(BaseModel):
    service: str
    owner: dict[str, Any]
    health: dict[str, Any]
    token_present: bool
    base_url: str | None = None
    host: str | None = None
    port: int | None = None
    pid: int | None = None
    repo_root: str | None = None
    started_at: str | None = None


class DaemonShutdownResponse(BaseModel):
    accepted: bool
    service: str
