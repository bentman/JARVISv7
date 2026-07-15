from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from backend.app.agents.specs import DEFAULT_SPECS_DIR, JarvisAgentSpec, load_agent_specs
from backend.app.core.paths import CONFIG_DIR
from pydantic import BaseModel, Field

DEFAULT_ROLES_PATH = CONFIG_DIR / "agents" / "roles.yaml"


class AgentRoleDefinition(BaseModel):
    role_id: str
    display_name: str
    description: str
    prompt_path: str
    allowed_message_types: list[str] = Field(default_factory=list)


def load_agent_roles(path: Path = DEFAULT_ROLES_PATH) -> dict[str, AgentRoleDefinition]:
    if path == DEFAULT_ROLES_PATH:
        return _roles_from_specs(load_agent_specs(DEFAULT_SPECS_DIR))
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
    return roles


def _roles_from_specs(specs: dict[str, JarvisAgentSpec]) -> dict[str, AgentRoleDefinition]:
    return {
        spec_id: AgentRoleDefinition(
            role_id=spec.spec_id,
            display_name=spec.display_name,
            description=spec.description,
            prompt_path=spec.prompt_path,
            allowed_message_types=spec.allowed_message_types,
        )
        for spec_id, spec in specs.items()
    }


def role_ids(roles: dict[str, AgentRoleDefinition] | None = None) -> list[str]:
    loaded_roles = roles or load_agent_roles()
    return sorted(loaded_roles)


def role_payload(roles: dict[str, AgentRoleDefinition] | None = None) -> list[dict[str, Any]]:
    loaded_roles = roles or load_agent_roles()
    return [loaded_roles[role_id].model_dump() for role_id in sorted(loaded_roles)]
