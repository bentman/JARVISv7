from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

from backend.app.agents.registry import AgentRegistry


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

    def invoke(
        self,
        profile_id: str,
        prompt: str,
        mode: str,
        engine_getter: Callable,
        operation: Any = None,
    ) -> AgentInvocationResult:
        profile = self._registry.get(profile_id)
        if profile is None:
            raise ValueError(f"unknown agent profile: {profile_id}")
        if mode not in profile.invocation_modes:
            raise ValueError(f"agent {profile_id} does not support {mode} invocation")
        return engine_getter().run_agent(profile, prompt, mode=mode, operation=operation)
