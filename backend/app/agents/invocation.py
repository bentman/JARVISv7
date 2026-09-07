from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from backend.app.agents.registry import AgentRegistry
from backend.app.agents.schema import AgentProfile


@dataclass(frozen=True, slots=True)
class AgentInvocationResult:
    agent_id: str
    status: str
    output: dict[str, Any]
    turn_id: str
    session_id: str
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AgentInvoker:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def invoke_direct(
        self, profile_id: str, prompt: str, engine_getter: Callable
    ) -> AgentInvocationResult:
        profile = self._registry.get(profile_id)
        if profile is None:
            raise ValueError(f"unknown agent profile: {profile_id}")
        if "direct" not in profile.invocation_modes:
            raise ValueError(
                f"agent {profile_id} does not support direct invocation"
            )
        engine = engine_getter()
        return engine.run_agent(profile, prompt, mode="direct")

    def invoke_as_tool(
        self, profile_id: str, prompt: str, engine_getter: Callable
    ) -> AgentInvocationResult:
        profile = self._registry.get(profile_id)
        if profile is None:
            raise ValueError(f"unknown agent profile: {profile_id}")
        if "as_tool" not in profile.invocation_modes:
            raise ValueError(
                f"agent {profile_id} does not support as_tool invocation"
            )
        engine = engine_getter()
        return engine.run_agent(profile, prompt, mode="as_tool")
