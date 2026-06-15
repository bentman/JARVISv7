from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from backend.app.agents.messages import AgentRole
from backend.app.core.paths import CONFIG_DIR

DEFAULT_ROLES_PATH = CONFIG_DIR / "agents" / "roles.yaml"
VALID_AGENT_ROLES: tuple[AgentRole, ...] = ("planner", "executor", "critic", "curator", "learner")


class AgentRoleDefinition(BaseModel):
    role_id: AgentRole
    display_name: str
    description: str
    prompt_path: str
    allowed_message_types: list[str] = Field(default_factory=list)


def load_agent_roles(path: Path = DEFAULT_ROLES_PATH) -> dict[str, AgentRoleDefinition]:
    if not path.exists():
        raise FileNotFoundError(f"agent roles config not found: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_roles = payload.get("roles")
    if not isinstance(raw_roles, list):
        raise ValueError("agent roles config must contain a roles list")
    roles: dict[str, AgentRoleDefinition] = {}
    for raw_role in raw_roles:
        if not isinstance(raw_role, dict):
            raise ValueError("each agent role must be a mapping")
        role = AgentRoleDefinition.model_validate(raw_role)
        if role.role_id in roles:
            raise ValueError(f"duplicate agent role: {role.role_id}")
        roles[role.role_id] = role
    missing = sorted(set(VALID_AGENT_ROLES) - set(roles))
    if missing:
        raise ValueError(f"agent roles config missing roles: {', '.join(missing)}")
    return roles


def role_ids(roles: dict[str, AgentRoleDefinition] | None = None) -> list[str]:
    loaded_roles = roles or load_agent_roles()
    return sorted(loaded_roles)


def role_payload(roles: dict[str, AgentRoleDefinition] | None = None) -> list[dict[str, Any]]:
    loaded_roles = roles or load_agent_roles()
    return [loaded_roles[role_id].model_dump() for role_id in sorted(loaded_roles)]
