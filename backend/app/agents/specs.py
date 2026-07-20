from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from backend.app.core.paths import CONFIG_DIR

DEFAULT_SPECS_DIR = CONFIG_DIR / "agents" / "specs"
_SPEC_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class JarvisAgentSpec(BaseModel):
    spec_id: str
    display_name: str
    description: str
    kind: Literal["system", "default", "user"] = "default"
    enabled: bool = False
    created_by: str = "repo"
    purpose: str
    instructions_summary: str
    allowed_message_types: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    handoff_policy: dict[str, Any] = Field(default_factory=dict)
    output_contract: dict[str, Any] = Field(default_factory=dict)
    guardrails: dict[str, Any] = Field(default_factory=dict)
    version: str = "1"

    @field_validator("spec_id")
    @classmethod
    def _validate_spec_id(cls, value: str) -> str:
        if not _SPEC_ID_PATTERN.fullmatch(value):
            raise ValueError("spec_id must be lowercase snake_case and start with a letter")
        return value


def load_agent_specs(directory: Path = DEFAULT_SPECS_DIR) -> dict[str, JarvisAgentSpec]:
    if not directory.exists():
        raise FileNotFoundError(f"agent specs directory not found: {directory}")
    specs: dict[str, JarvisAgentSpec] = {}
    for path in sorted(directory.glob("*.yaml")):
        spec = load_agent_spec_file(path)
        if spec.spec_id in specs:
            raise ValueError(f"duplicate agent spec: {spec.spec_id}")
        specs[spec.spec_id] = spec
    return specs


def load_agent_spec_file(path: Path) -> JarvisAgentSpec:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"agent spec must be a mapping: {path}")
    return JarvisAgentSpec.model_validate(payload)
