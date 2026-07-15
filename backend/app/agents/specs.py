from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import yaml
from backend.app.core.paths import CONFIG_DIR, REPO_ROOT
from pydantic import BaseModel, Field, field_validator

DEFAULT_SPECS_DIR = CONFIG_DIR / "agents" / "specs"
AGENT_PROMPTS_DIR = CONFIG_DIR / "prompts" / "agents"
_SPEC_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class JarvisAgentSpec(BaseModel):
    spec_id: str
    display_name: str
    description: str
    kind: Literal["system", "default", "user"] = "default"
    enabled: bool = False
    created_by: str = "repo"
    prompt_path: str
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

    @field_validator("prompt_path")
    @classmethod
    def _validate_prompt_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute():
            raise ValueError("prompt_path must be repo-relative")
        resolved = (REPO_ROOT / path).resolve()
        try:
            resolved.relative_to(AGENT_PROMPTS_DIR.resolve())
        except ValueError as exc:
            raise ValueError("prompt_path must stay under config/prompts/agents") from exc
        if resolved.suffix != ".md":
            raise ValueError("prompt_path must reference a markdown prompt")
        return value.replace("\\", "/")


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


def write_agent_spec(spec: JarvisAgentSpec, directory: Path = DEFAULT_SPECS_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{spec.spec_id}.yaml"
    payload = spec.model_dump()
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def spec_ids(specs: dict[str, JarvisAgentSpec] | None = None) -> list[str]:
    loaded_specs = specs or load_agent_specs()
    return sorted(loaded_specs)


def spec_payload(specs: dict[str, JarvisAgentSpec] | None = None) -> list[dict[str, Any]]:
    loaded_specs = specs or load_agent_specs()
    return [loaded_specs[spec_id].model_dump() for spec_id in sorted(loaded_specs)]
