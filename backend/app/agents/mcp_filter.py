"""Agent-scoped MCP filtering.

Ensures agents only see MCP resources, tools, and prompts permitted by
their profile's capability_ids and the connection's own allowlists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.agents.schema import AgentProfile
from backend.app.extensions.mcp import McpConnectionDefinition

_MCP_CAPABILITY_PREFIX = "mcp-"


@dataclass(frozen=True, slots=True)
class AgentMcpPolicy:
    agent_id: str
    allowed_connections: tuple[str, ...]
    allowed_tools: tuple[str, ...] = ()
    allowed_resources: tuple[str, ...] = ()
    allowed_prompts: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.agent_id, str) or not self.agent_id.strip():
            raise ValueError("agent_id must be a non-empty string")
        for field_name in (
            "allowed_connections",
            "allowed_tools",
            "allowed_resources",
            "allowed_prompts",
        ):
            values = getattr(self, field_name)
            if not isinstance(values, tuple):
                raise ValueError(f"{field_name} must be a tuple")
            for item in values:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError(f"{field_name} entries must be non-empty strings")

    def can_access(self, connection_id: str) -> bool:
        """Whether this agent may use the given MCP connection."""
        return connection_id in self.allowed_connections

    def filter_tools(
        self, connection_id: str, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter tool list for this agent on the given connection.

        If connection_id is not allowed, return empty. Otherwise intersect
        with allowed_tools (if non-empty) using the "name" key.
        """
        if not self.can_access(connection_id):
            return []
        return _filter_by_key(tools, self.allowed_tools, "name")

    def filter_resources(
        self, connection_id: str, resources: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter resource list for this agent on the given connection."""
        if not self.can_access(connection_id):
            return []
        return _filter_by_key(resources, self.allowed_resources, "uri")

    def filter_prompts(
        self, connection_id: str, prompts: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Filter prompt list for this agent on the given connection."""
        if not self.can_access(connection_id):
            return []
        return _filter_by_key(prompts, self.allowed_prompts, "name")


def _filter_by_key(
    items: list[dict[str, Any]],
    allowlist: tuple[str, ...],
    key: str,
) -> list[dict[str, Any]]:
    """Return items whose `key` value is in `allowlist`.

    If `allowlist` is empty, all items pass through (no additional filter).
    """
    if not allowlist:
        return list(items)
    allowed_set = set(allowlist)
    return [item for item in items if item.get(key) in allowed_set]


def build_agent_mcp_policy(
    agent_profile: AgentProfile,
    mcp_connections: list[McpConnectionDefinition] | None = None,
) -> AgentMcpPolicy | None:
    """Build a policy from an AgentProfile's capability_ids.

    Extracts MCP connection IDs from capability IDs that start with "mcp-".
    Returns None if no MCP-related capabilities are found.
    """
    mcp_connection_ids = tuple(
        cap_id[len(_MCP_CAPABILITY_PREFIX):]
        for cap_id in agent_profile.capability_ids
        if isinstance(cap_id, str) and cap_id.startswith(_MCP_CAPABILITY_PREFIX)
    )
    if not mcp_connection_ids:
        return None

    allowed_connections: list[str] = []
    if mcp_connections is not None:
        available_ids = {conn.connection_id for conn in mcp_connections}
        allowed_connections = [cid for cid in mcp_connection_ids if cid in available_ids]
    else:
        allowed_connections = list(mcp_connection_ids)

    if not allowed_connections:
        return None

    return AgentMcpPolicy(
        agent_id=agent_profile.profile_id,
        allowed_connections=tuple(allowed_connections),
    )


__all__ = [
    "AgentMcpPolicy",
    "build_agent_mcp_policy",
]
