from __future__ import annotations

from typing import Any

from backend.app.agents.registry import AgentRegistry
from backend.app.agents.router import AgentRouter
from backend.app.agents.schema import AgentProfile


def _profile(**overrides: Any) -> AgentProfile:
    values: dict[str, Any] = {
        "profile_id": "test-agent",
        "display_name": "Test Agent",
        "purpose": "A test agent for validation",
        "instructions": "Follow test conventions.",
        "invocation_modes": ("router_selected",),
        "capability_ids": (),
        "memory_scope": "working",
        "approval_class": "standard",
        "timeout_ms": 30000,
        "cancellable": True,
        "output_contract": {"type": "object"},
        "provider_model_policy": {},
    }
    values.update(overrides)
    return AgentProfile(**values)


def test_select_returns_matching_profile_for_keyword() -> None:
    profile = _profile(
        profile_id="researcher",
        purpose="Research and summarize documents",
        invocation_modes=("router_selected",),
    )
    registry = AgentRegistry()
    registry._profiles = [profile]

    router = AgentRouter(registry)
    result = router.select("Please research this topic for me")

    assert result is not None
    assert result.profile_id == "researcher"


def test_select_returns_none_when_no_match() -> None:
    profile = _profile(
        profile_id="coder",
        purpose="Write and debug code",
        invocation_modes=("router_selected",),
    )
    registry = AgentRegistry()
    registry._profiles = [profile]

    router = AgentRouter(registry)
    result = router.select("What is the weather today")

    assert result is None


def test_candidates_returns_only_router_selected_profiles() -> None:
    direct = _profile(
        profile_id="direct-agent",
        invocation_modes=("direct",),
    )
    routed = _profile(
        profile_id="routed-agent",
        invocation_modes=("router_selected",),
    )
    both = _profile(
        profile_id="both-agent",
        invocation_modes=("direct", "router_selected"),
    )
    registry = AgentRegistry()
    registry._profiles = [direct, routed, both]

    router = AgentRouter(registry)
    candidates = router.candidates()

    assert len(candidates) == 2
    ids = {c.profile_id for c in candidates}
    assert ids == {"routed-agent", "both-agent"}


def test_empty_registry_returns_none() -> None:
    registry = AgentRegistry()
    router = AgentRouter(registry)

    result = router.select("anything at all")
    assert result is None


def test_select_ignores_short_keywords() -> None:
    profile = _profile(
        profile_id="short-purpose",
        purpose="Run it",
        invocation_modes=("router_selected",),
    )
    registry = AgentRegistry()
    registry._profiles = [profile]

    router = AgentRouter(registry)
    # "run" is 3 chars (passes > 2 filter), but "it" is 2 chars (filtered out)
    result = router.select("please run the test")
    assert result is not None

    result_no_match = router.select("please walk the dog")
    assert result_no_match is None


def test_select_returns_first_match() -> None:
    first = _profile(
        profile_id="first-agent",
        purpose="Analyze data and produce reports",
        invocation_modes=("router_selected",),
    )
    second = _profile(
        profile_id="second-agent",
        purpose="Analyze images and produce thumbnails",
        invocation_modes=("router_selected",),
    )
    registry = AgentRegistry()
    registry._profiles = [first, second]

    router = AgentRouter(registry)
    result = router.select("Please analyze this dataset")

    assert result is not None
    assert result.profile_id == "first-agent"
