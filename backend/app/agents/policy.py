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

    def allows_role(self, role_id: str) -> bool:
        return self.enabled and role_id in self.allowed_roles

    def allows_tool(self, tool_name: str) -> bool:
        return self.enabled and tool_name in self.allowed_tools


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
