from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.agents.registry import DISABLED, AgentRegistry
from backend.app.agents.schema import AgentProfile

# The router selects an agent only when the user addresses one by name, so ordinary turns
# never change hands on a guess.
_ADDRESS_FORMS = (
    r"^(?:hey\s+)?{name}\s*[,:]\s*(?P<task>\S.*)$",
    r"^hey\s+{name}\s+(?P<task>\S.*)$",
    r"^(?:please\s+)?ask\s+{name}\s+to\s+(?P<task>\S.*)$",
    r"^@{name}\s+(?P<task>\S.*)$",
)
_HANDOFF_FORM = (
    r"^(?:please\s+)?(?:hand\s+(?:me\s+)?(?:over|off)\s+to|talk\s+to|switch\s+to)"
    r"\s+{name}(?:\s+please)?[.!]?$"
)
_END_HANDOFF = re.compile(
    r"(?:(?:go\s+)?back\s+to\s+jarvis|(?:end|stop)\s+(?:the\s+)?handoff)[.!]?",
    re.IGNORECASE,
)


_HOW_TO_ENABLE = "Turn that on for it in Agents, or duplicate it there first if it is built in."
_MODE_REFUSALS = {
    "router_selected": f"isn't set to answer when addressed by name. {_HOW_TO_ENABLE}",
    "handoff": f"isn't set to take over the conversation. {_HOW_TO_ENABLE}",
}


@dataclass(frozen=True, slots=True)
class AgentRoute:
    """An agent the user addressed; `reason` explains why it cannot take the turn."""

    profile: AgentProfile
    task: str
    reason: str = ""


def ends_handoff(text: str) -> bool:
    return bool(_END_HANDOFF.fullmatch(text.strip()))


class AgentRouter:
    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    def route(self, text: str) -> AgentRoute | None:
        return self._match(text, _ADDRESS_FORMS, "router_selected")

    def handoff_request(self, text: str) -> AgentRoute | None:
        return self._match(text, (_HANDOFF_FORM,), "handoff")

    def ineligible_reason(self, profile: AgentProfile, mode: str) -> str:
        if not self._registry.enabled(profile.profile_id):
            return DISABLED
        if profile.runtime_kind != "internal":
            return f"{profile.display_name} runs in an external agent and is reachable only directly."
        if mode not in profile.invocation_modes:
            return f"{profile.display_name} {_MODE_REFUSALS[mode]}"
        return self._registry.unavailable_reason(profile)

    def _match(self, text: str, forms: tuple[str, ...], mode: str) -> AgentRoute | None:
        utterance = text.strip()
        for name, profile in self._names():
            pattern = re.escape(name).replace(r"\ ", r"\s+")
            for form in forms:
                match = re.match(form.format(name=pattern), utterance, re.IGNORECASE | re.DOTALL)
                if match:
                    task = match.groupdict().get("task", "").strip()
                    return AgentRoute(profile, task, self.ineligible_reason(profile, mode))
        return None

    def _names(self) -> list[tuple[str, AgentProfile]]:
        names: dict[str, AgentProfile] = {}
        for profile in self._registry.profiles():
            for name in (profile.display_name, profile.profile_id.replace("-", " "), profile.profile_id):
                names.setdefault(name.strip().lower(), profile)
        # Longest first, so "notes pro" is never read as "notes" addressing "pro ...".
        return sorted(names.items(), key=lambda item: -len(item[0]))
