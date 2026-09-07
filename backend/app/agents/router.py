from __future__ import annotations

from typing import Any

from backend.app.agents.registry import AgentRegistry
from backend.app.agents.schema import AgentProfile


class AgentRouter:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def select(
        self, request_text: str, context: dict[str, Any] | None = None
    ) -> AgentProfile | None:
        text_lower = request_text.lower()
        for profile in self.candidates():
            keywords = profile.purpose.lower().split()
            if any(keyword in text_lower for keyword in keywords if len(keyword) > 2):
                return profile
        return None

    def candidates(self) -> list[AgentProfile]:
        return [
            p
            for p in self._registry.profiles()
            if "router_selected" in p.invocation_modes
        ]
