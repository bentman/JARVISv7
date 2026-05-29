from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class DiagnosticsProfileResponse(BaseModel):
    profile: dict[str, Any]
    flags: dict[str, Any]


class DiagnosticsPreflightResponse(BaseModel):
    tokens: list[str]
    dll_discovery_log: list[str]
    probe_errors: dict[str, str]


class DiagnosticsAudioIngressResponse(BaseModel):
    usable: bool
    sample_rate: int
    sample_count: int
    dtype: str | None
    duration: float
    input_device: str | None
    rms: float
    peak: float
    reason: str
