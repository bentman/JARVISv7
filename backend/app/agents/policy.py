from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from backend.app.core.paths import CONFIG_DIR

DEFAULT_POLICY_PATH = CONFIG_DIR / "app" / "policies.yaml"


class AgentPolicy(BaseModel):
    enabled: bool = False
    read_only: bool = True
    reason: str = "Agent boundary is disabled by policy"
    allowed_roles: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)


def load_agent_policy(path: Path = DEFAULT_POLICY_PATH) -> AgentPolicy:
    if not path.exists():
        return AgentPolicy()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_policy = payload.get("agents", {})
    if raw_policy is None:
        raw_policy = {}
    if not isinstance(raw_policy, dict):
        raise ValueError("agents policy must be a mapping")
    return AgentPolicy.model_validate(raw_policy)
