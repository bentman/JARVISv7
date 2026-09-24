from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from backend.app.agents.registry import AgentRegistry
from backend.app.agents.router import AgentRouter, ends_handoff
from backend.app.agents.schema import AgentProfile


def _profile(**overrides: Any) -> AgentProfile:
    values: dict[str, Any] = {
        "profile_id": "meeting-notes",
        "display_name": "Notes",
        "purpose": "Tidy meeting notes",
        "instructions": "Answer briefly.",
        "invocation_modes": ("router_selected", "handoff"),
        "capability_ids": (),
        "memory_scope": "none",
        "approval_class": "none",
        "timeout_ms": 30000,
        "cancellable": True,
        "output_contract": {"type": "object"},
        "provider_model_policy": {},
    }
    values.update(overrides)
    return AgentProfile(**values)


def _router(*profiles: AgentProfile, overlay: Any = None) -> AgentRouter:
    registry = AgentRegistry(overlay=overlay)
    registry._profiles = list(profiles)
    return AgentRouter(registry)


@pytest.mark.parametrize(
    "utterance",
    [
        "Notes, tidy these bullets",
        "notes: tidy these bullets",
        "Hey Notes tidy these bullets",
        "please ask notes to tidy these bullets",
        "@meeting-notes tidy these bullets",
        "Meeting notes, tidy these bullets",
    ],
)
def test_an_agent_addressed_by_name_takes_the_task(utterance: str) -> None:
    route = _router(_profile()).route(utterance)

    assert route is not None
    assert (route.profile.profile_id, route.task, route.reason) == (
        "meeting-notes", "tidy these bullets", "",
    )


@pytest.mark.parametrize(
    "utterance",
    [
        "What do my notes say about the budget?",
        "Notesworthy, tidy these",
        "Notes",
        "",
    ],
)
def test_a_turn_that_does_not_address_an_agent_stays_with_the_assistant(utterance: str) -> None:
    assert _router(_profile()).route(utterance) is None


def test_the_longest_name_wins_when_names_share_a_prefix() -> None:
    short = _profile(profile_id="notes", display_name="Notes")
    long = _profile(profile_id="notes-pro", display_name="Notes Pro")

    route = _router(short, long).route("Notes Pro, draft the summary")

    assert route is not None and route.profile.profile_id == "notes-pro"


@pytest.mark.parametrize(
    ("profile", "overlay", "reason"),
    [
        (_profile(invocation_modes=("direct",)), None, "isn't set to answer when addressed by name"),
        (
            _profile(invocation_modes=("direct", "router_selected"), runtime={"kind": "acp", "adapter_id": "coder"}),
            None,
            "reachable only directly",
        ),
        (
            _profile(),
            SimpleNamespace(read=lambda _id: SimpleNamespace(state="disabled")),
            "Agent is disabled.",
        ),
    ],
)
def test_an_addressed_agent_that_cannot_take_the_turn_says_why(
    profile: AgentProfile, overlay: Any, reason: str
) -> None:
    route = _router(profile, overlay=overlay).route("Notes, tidy these")

    assert route is not None
    assert reason in route.reason


@pytest.mark.parametrize(
    "utterance",
    ["Hand me over to Notes", "hand off to notes.", "Talk to Notes please", "switch to meeting notes"],
)
def test_a_handoff_request_names_the_agent(utterance: str) -> None:
    request = _router(_profile()).handoff_request(utterance)

    assert request is not None
    assert (request.profile.profile_id, request.reason) == ("meeting-notes", "")


def test_a_handoff_to_an_agent_without_the_mode_is_refused_with_a_reason() -> None:
    request = _router(_profile(invocation_modes=("router_selected",))).handoff_request("talk to Notes")

    assert request is not None
    assert "isn't set to take over the conversation" in request.reason


def test_talking_about_an_agent_is_not_a_handoff() -> None:
    assert _router(_profile()).handoff_request("talk to Notes about the budget") is None


@pytest.mark.parametrize(
    ("utterance", "ends"),
    [
        ("Back to JARVIS", True),
        ("go back to jarvis.", True),
        ("end handoff", True),
        ("Stop the handoff!", True),
        ("I want to go back to Jarvis later", False),
    ],
)
def test_the_end_of_a_handoff_is_an_exact_phrase(utterance: str, ends: bool) -> None:
    assert ends_handoff(utterance) is ends
