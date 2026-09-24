"""The turn engine selects, governs, and grounds one extension capability per turn."""

from __future__ import annotations

from typing import Any

import pytest
from backend.app.actions.catalog import CapabilityObservation
from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.session_manager import SessionManager
from backend.app.personality.loader import load_default_personality
from backend.app.runtimes.llm.base import LLMBase, ToolCall, ToolCallResult
from backend.app.services.capability_service import CapabilityService
from backend.app.services.llm_execution_coordinator import LLMExecutionCoordinator

pytestmark = [pytest.mark.turn]

WRITE = "extension-write"
READ = "extension-read"


class ToolModel(LLMBase):
    """A model that selects a tool the first time it is offered any."""

    def __init__(self, call: ToolCall | None = None, answer: str = "Grounded answer.") -> None:
        self.call = call
        self.answer = answer
        self.offered: list[tuple[str, ...]] = []
        self.grounded: list[Any] = []

    def generate(self, prompt: str, **kwargs: object) -> str:
        return self.answer

    def generate_envelope(self, envelope, **kwargs):
        self.grounded.append(envelope)
        return self.answer

    def generate_structured(self, envelope, schema):
        return '{"action":"none","topic":"","queries":[],"private":false,"message":""}'

    def generate_with_tools(self, envelope, tools, **kwargs) -> ToolCallResult:
        self.offered.append(tuple(tool.name for tool in tools))
        if self.call is None:
            return ToolCallResult(text=self.answer)
        call, self.call = self.call, None
        return ToolCallResult(call=call)

    def is_available(self) -> bool:
        return True

    def runtime_name(self) -> str:
        return "tool-model"

    def context_window(self) -> int:
        return 8192


class PlainModel(ToolModel):
    """A runtime with no tool protocol at all."""

    generate_with_tools = LLMBase.generate_with_tools


class Runtime:
    """Stands in for ExtensionRuntimeService's model-facing catalog."""

    def __init__(self, entries: list[dict[str, Any]] | None = None) -> None:
        self.entries = entries if entries is not None else [
            {"capability_id": READ, "extension_id": "mcp:probe", "name": "discover",
             "input_schema": {"type": "object"}},
            {"capability_id": WRITE, "extension_id": "tool:writer", "name": "run",
             "input_schema": {"type": "object"}},
        ]
        self.runs = type("Runs", (), {"list": staticmethod(lambda: [])})()
        self.hooks = type("Hooks", (), {"emit": staticmethod(lambda *a, **k: [])})()

    def tool_catalog(self) -> list[dict[str, Any]]:
        return list(self.entries)


def _capabilities(results: dict[str, Any] | None = None, observe=None) -> CapabilityService:
    from backend.app.actions.contracts import (
        CapabilityDescriptor,
        default_authorization,
    )

    outcomes = results or {}

    def descriptor(capability_id: str, effect: str) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability_id=capability_id, source="test", provenance="test",
            input_schema={"type": "object"}, effect_class=effect, readiness="ready",  # type: ignore[arg-type]
            availability="available", execution_owner="backend.extension_runtime",
            authorization_rule=default_authorization(effect),  # type: ignore[arg-type]
            timeout_policy={"timeout_ms": 5000}, cancellation_policy={"cancellable": True},
            result_schema={"type": "object"}, artifact_evidence={"records": True},
            unavailable_explanation="",
            boundaries={"storage_roots": ["data"], "timeout_ms": 5000, "cancellable": True,
                        "max_result_bytes": 64000},
            metadata_claims={"definition": {"sha256": "abc", "trusted": False}},
        )

    def handler(capability_id: str):
        def run(arguments: dict[str, Any], _operation: Any) -> dict[str, Any]:
            outcome = outcomes.get(capability_id, {"ok": True})
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        return run

    service = CapabilityService(
        observe=observe or (lambda: CapabilityObservation(extension_catalog_present=True))
    )
    service.bind_extensions(lambda: [
        (descriptor(READ, "external_read"), handler(READ)),
        (descriptor(WRITE, "external_write"), handler(WRITE)),
    ])
    return service


def engine_at(tmp_path, model, runtime=None, capabilities=None):
    manager = SessionManager(
        turns_base_dir=tmp_path / "turns", sessions_base_dir=tmp_path / "sessions"
    )
    engine = TurnEngine(
        stt=None, tts=None, llm=model, personality=load_default_personality(),  # type: ignore[arg-type]
        session_manager=manager, llm_coordinator=LLMExecutionCoordinator(),
        capability_service=capabilities or _capabilities(),
        extension_runtime=runtime if runtime is not None else Runtime(),
    )
    return engine, manager


def test_a_model_that_selects_nothing_answers_without_action_evidence(tmp_path):
    engine, manager = engine_at(tmp_path, ToolModel())
    turn = engine.run_text_turn("Hello there")

    assert turn.response_text == "Grounded answer."
    artifact = manager.turn_artifacts[0]
    assert artifact.action_proposals == []
    assert artifact.tools_invoked == []


def test_an_allowed_capability_runs_and_grounds_its_result(tmp_path):
    model = ToolModel(call=ToolCall(READ, {}))
    engine, manager = engine_at(tmp_path, model)

    turn = engine.run_text_turn("Look something up")

    artifact = manager.turn_artifacts[0]
    assert artifact.tools_invoked == [READ]
    assert [record["capability_id"] for record in artifact.action_execution_results] == [READ]
    assert artifact.action_execution_results[0]["status"] == "success"
    # The result re-enters the prompt as untrusted tool_result context.
    grounded = model.grounded[-1]
    assert any(segment.content_type == "tool_result" for segment in grounded.segments)
    assert turn.response_text == "Grounded answer."


def test_a_capability_needing_approval_asks_first_and_does_not_run(tmp_path):
    engine, manager = engine_at(tmp_path, ToolModel(call=ToolCall(WRITE, {})))

    turn = engine.run_text_turn("Write something")

    assert "Reply yes to confirm" in turn.response_text
    artifact = manager.turn_artifacts[0]
    assert artifact.action_execution_results == []
    assert artifact.authorization_decisions[0]["outcome"] == "approval_required"
    assert artifact.tools_invoked == []


def test_confirming_on_the_next_turn_executes_and_records_the_approval(tmp_path):
    engine, manager = engine_at(tmp_path, ToolModel(call=ToolCall(WRITE, {})))
    engine.run_text_turn("Write something")

    turn = engine.run_text_turn("yes")

    artifact = manager.turn_artifacts[1]
    assert [record["outcome"] for record in artifact.approval_records] == ["approved"]
    assert artifact.action_execution_results[0]["status"] == "success"
    assert artifact.tools_invoked == [WRITE]
    assert turn.failure_reason is None


def test_declining_records_a_denial_and_runs_nothing(tmp_path):
    engine, manager = engine_at(tmp_path, ToolModel(call=ToolCall(WRITE, {})))
    engine.run_text_turn("Write something")

    turn = engine.run_text_turn("no")

    assert turn.response_text == "Cancelled."
    artifact = manager.turn_artifacts[1]
    assert [record["outcome"] for record in artifact.approval_records] == ["denied"]
    assert artifact.action_execution_results == []


def test_an_unanswered_approval_lapses_at_the_turn_boundary(tmp_path):
    engine, manager = engine_at(tmp_path, ToolModel(call=ToolCall(WRITE, {})))
    engine.run_text_turn("Write something")

    engine.run_text_turn("something else entirely")

    artifact = manager.turn_artifacts[1]
    assert artifact.action_cancellations[0]["cancelled_by"] == "turn_boundary"
    assert artifact.action_execution_results == []


def test_a_failing_capability_is_explained_rather_than_hidden(tmp_path):
    capabilities = _capabilities({READ: RuntimeError("connection refused")})
    engine, manager = engine_at(tmp_path, ToolModel(call=ToolCall(READ, {})), capabilities=capabilities)

    turn = engine.run_text_turn("Look something up")

    assert "could not complete" in turn.response_text.casefold()
    assert manager.turn_artifacts[0].action_execution_results[0]["status"] == "failure"


def test_acp_operations_are_never_offered(tmp_path):
    runtime = Runtime([
        {"capability_id": READ, "extension_id": "acp:agent", "name": "prompt",
         "input_schema": {"type": "object"}},
    ])
    # tool_catalog is the real filter; this proves the engine offers what it returns.
    model = ToolModel()
    engine, _ = engine_at(tmp_path, model, runtime=runtime)
    engine.run_text_turn("Hello there")
    assert model.offered and all("acp" not in name for name in model.offered[0])


def test_a_runtime_without_tool_calling_takes_the_plain_path(tmp_path):
    model = PlainModel()
    engine, manager = engine_at(tmp_path, model)

    turn = engine.run_text_turn("Hello there")

    assert turn.response_text == "Grounded answer."
    assert model.offered == []
    assert manager.turn_artifacts[0].action_proposals == []


def test_a_rejected_tool_offer_still_answers_and_records_why(tmp_path):
    class Rejecting(ToolModel):
        def generate_with_tools(self, envelope, tools, **kwargs):
            raise RuntimeError("llama.cpp chat completion failed: failed to parse grammar")

    engine, manager = engine_at(tmp_path, Rejecting())

    turn = engine.run_text_turn("Hello there")

    assert turn.response_text == "Grounded answer."
    assert "failed to parse grammar" in manager.turn_artifacts[0].runtime_context["tool_selection_error"]


def test_only_one_capability_runs_per_turn(tmp_path):
    class Greedy(ToolModel):
        def generate_with_tools(self, envelope, tools, **kwargs):
            self.offered.append(tuple(tool.name for tool in tools))
            return ToolCallResult(call=ToolCall(READ, {}))

    engine, manager = engine_at(tmp_path, Greedy())
    engine.run_text_turn("Look something up")

    assert manager.turn_artifacts[0].tools_invoked == [READ]


DEFAULT_AGENTS = {"helper": (["as_tool"], "none"), "direct-only": (["direct"], "none")}


def _agent_engine(tmp_path, model, agents_by_id=None, states=None, fields=None, runtime=None):
    """An engine with file-backed agents.

    `states` maps extension ids to overlay states; `fields` adds profile fields per agent id.
    """
    from types import SimpleNamespace

    import yaml
    from backend.app.agents.registry import AgentRegistry
    from backend.app.services.capability_service import build_agent_handlers

    agents = tmp_path / "config" / "agents"
    agents.mkdir(parents=True)
    for profile_id, (modes, approval) in (agents_by_id or DEFAULT_AGENTS).items():
        (agents / f"{profile_id}.yaml").write_text(yaml.safe_dump({
            "profile_id": profile_id, "display_name": profile_id.title(),
            "purpose": "Helps with notes", "instructions": "Answer briefly.",
            "invocation_modes": modes, "capability_ids": [], "memory_scope": "none",
            "approval_class": approval, "timeout_ms": 5000, "cancellable": True,
            "output_contract": {"type": "object"}, "provider_model_policy": {},
            **(fields or {}).get(profile_id, {}),
        }), encoding="utf-8")
    overlay_states = states if states is not None else {}
    overlay = SimpleNamespace(
        read=lambda extension_id: SimpleNamespace(state=overlay_states[extension_id])
        if extension_id in overlay_states
        else None
    )
    registry = AgentRegistry(tmp_path / "config", overlay=overlay)
    capabilities = _capabilities(observe=lambda: CapabilityObservation(
        extension_catalog_present=True, agents=tuple(registry.to_capability_records()),
    ))
    engine, manager = engine_at(
        tmp_path, model, runtime=runtime if runtime is not None else Runtime([]),
        capabilities=capabilities,
    )
    engine.agent_registry = registry
    capabilities.bind_handler_provider(lambda: build_agent_handlers(
        agent_registry_provider=lambda: registry, engine_provider=lambda: engine,
    ))
    return engine, manager


def test_an_as_tool_agent_runs_inside_the_proposing_turn_with_delegated_run_evidence(tmp_path):
    model = ToolModel(call=ToolCall("agent-invoke-helper", {"prompt": "tidy my notes"}))
    engine, manager = _agent_engine(tmp_path, model)

    turn = engine.run_text_turn("Tidy my notes")

    assert model.offered[0] == ("agent-invoke-helper",)
    assert turn.response_text == "Grounded answer."
    artifact = manager.turn_artifacts[0]
    assert len(manager.turn_artifacts) == 1
    assert [record["status"] for record in artifact.action_execution_results] == ["success"]
    [run] = artifact.delegated_runs
    assert (run["kind"], run["target_id"], run["runtime"], run["mode"], run["status"]) == (
        "agent", "helper", "internal", "as_tool", "success",
    )
    assert run["turn_id"] == artifact.turn_id


def test_an_as_tool_agent_call_is_refused_outside_the_turn_that_proposed_it(tmp_path):
    engine, _ = _agent_engine(tmp_path, ToolModel())
    profile = engine.agent_registry.get("helper")

    with pytest.raises(RuntimeError, match="inside the turn that delegated it"):
        engine.run_agent(profile, "tidy", mode="as_tool", operation=None)


def test_an_addressed_agent_answers_the_turn_with_router_evidence(tmp_path):
    model = ToolModel(answer="Agent answer.")
    engine, manager = _agent_engine(tmp_path, model, {"notes": (["router_selected"], "none")})

    turn = engine.run_text_turn("Notes, tidy these bullets")

    assert turn.response_text == "Agent answer."
    assert model.offered == [], "a routed turn is answered by the agent, not offered tools"
    artifact = manager.turn_artifacts[0]
    assert artifact.runtime_context["agent_route"] == {
        "outcome": "selected", "profile_id": "notes", "reason": "",
    }
    [run] = artifact.delegated_runs
    assert (run["target_id"], run["mode"], run["status"]) == ("notes", "router_selected", "success")
    assert [proposal["proposed_by"] for proposal in artifact.action_proposals] == ["router"]


def test_a_routed_agent_that_needs_approval_asks_first_and_answers_on_yes(tmp_path):
    model = ToolModel(answer="Agent answer.")
    engine, manager = _agent_engine(tmp_path, model, {"notes": (["router_selected"], "standard")})

    asked = engine.run_text_turn("Notes, tidy these bullets")
    answered = engine.run_text_turn("yes")

    assert asked.response_text == "May I hand this to Notes? Reply yes to confirm."
    assert manager.turn_artifacts[0].delegated_runs == []
    assert answered.response_text == "Agent answer."
    second = manager.turn_artifacts[1]
    assert [record["outcome"] for record in second.approval_records] == ["approved"]
    assert [run["mode"] for run in second.delegated_runs] == ["router_selected"]


def test_an_addressed_agent_that_is_disabled_falls_back_to_the_assistant(tmp_path):
    engine, manager = _agent_engine(
        tmp_path, ToolModel(), {"notes": (["router_selected"], "none")},
        states={"agent:notes": "disabled"},
    )

    turn = engine.run_text_turn("Notes, tidy these bullets")

    assert turn.response_text == "Grounded answer."
    artifact = manager.turn_artifacts[0]
    assert artifact.runtime_context["agent_route"] == {
        "outcome": "unavailable", "profile_id": "notes", "reason": "Agent is disabled.",
    }
    assert artifact.delegated_runs == []


def test_a_handoff_routes_every_turn_to_the_agent_until_the_user_returns(tmp_path):
    from unittest.mock import MagicMock

    model = ToolModel(answer="Agent answer.")
    engine, manager = _agent_engine(tmp_path, model, {"notes": (["handoff"], "none")})
    engine.search_service = MagicMock()

    started = engine.run_text_turn("Talk to Notes")
    handed = engine.run_text_turn("search the web for the meeting agenda")
    ended = engine.run_text_turn("Back to JARVIS")

    assert started.response_text.startswith("You're now talking to Notes.")
    assert handed.response_text == "Agent answer."
    engine.search_service.operation.assert_not_called()
    assert [run["mode"] for run in manager.turn_artifacts[1].delegated_runs] == ["handoff"]
    assert ended.response_text == "Back to JARVIS."
    assert engine.active_handoff() is None
    assert [
        event["event"]
        for artifact in manager.turn_artifacts
        for event in artifact.runtime_context.get("agent_handoff", [])
    ] == ["started", "ended"]


def test_a_handoff_to_an_agent_that_needs_approval_starts_only_on_yes(tmp_path):
    engine, manager = _agent_engine(
        tmp_path, ToolModel(answer="Agent answer."), {"notes": (["handoff"], "standard")}
    )

    asked = engine.run_text_turn("Hand me over to Notes")
    assert asked.response_text == "May I hand you over to Notes? Reply yes to confirm."
    assert engine.active_handoff() is None

    engine.run_text_turn("yes")
    handoff = engine.active_handoff()
    assert handoff is not None and handoff.approval_id

    handed = engine.run_text_turn("tidy these bullets")
    assert handed.response_text == "Agent answer."
    third = manager.turn_artifacts[2]
    assert [record["status"] for record in third.action_execution_results] == ["success"]
    assert [run["mode"] for run in third.delegated_runs] == ["handoff"]


def test_a_handoff_ends_and_says_why_when_the_agent_becomes_unavailable(tmp_path):
    states: dict[str, str] = {}
    engine, manager = _agent_engine(
        tmp_path, ToolModel(), {"notes": (["handoff"], "none")}, states=states
    )
    engine.run_text_turn("Talk to Notes")

    states["agent:notes"] = "disabled"
    turn = engine.run_text_turn("tidy these bullets")

    assert turn.response_text.startswith("Notes is no longer available (Agent is disabled.)")
    assert turn.response_text.endswith("Grounded answer.")
    assert engine.active_handoff() is None
    assert manager.turn_artifacts[1].runtime_context["agent_handoff"] == [
        {"event": "ended", "profile_id": "notes", "reason": "Agent is disabled."}
    ]


@pytest.mark.parametrize(
    ("scope", "layers"),
    [
        ("none", None),
        ("working", (False, False)),
        ("episodic", (True, False)),
        ("semantic", (False, True)),
        ("full", (True, True)),
    ],
)
def test_an_agent_reads_only_the_memory_layers_its_scope_allows(tmp_path, scope, layers):
    from types import SimpleNamespace

    engine, manager = _agent_engine(
        tmp_path, ToolModel(answer="Agent answer."), {"notes": (["router_selected"], "none")},
        fields={"notes": {"memory_scope": scope}},
    )
    episodic, semantic = object(), object()
    engine.episodic, engine.semantic = episodic, semantic
    calls = []
    engine.retrieval = SimpleNamespace(retrieve=lambda **kwargs: calls.append(kwargs) or [])

    engine.run_text_turn("Notes, tidy these bullets")

    agent_calls = [call for call in calls if call["query"] == "tidy these bullets"]
    context = manager.turn_artifacts[0].runtime_context
    if layers is None:
        assert "agent_memory" not in context
        assert agent_calls == []
        return
    assert context["agent_memory"] == {"profile_id": "notes", "scope": scope, "retrieved": []}
    expected = [(call["episodic"] is episodic, call["semantic"] is semantic) for call in agent_calls]
    assert expected == ([layers] if any(layers) else [])


def test_an_agent_runs_an_allowed_capability_and_answers_from_its_result(tmp_path):
    model = ToolModel(call=ToolCall(READ, {}), answer="Agent answer.")
    engine, manager = _agent_engine(
        tmp_path, model, {"notes": (["router_selected"], "none")},
        fields={"notes": {"capability_ids": [READ]}}, runtime=Runtime(),
    )

    turn = engine.run_text_turn("Notes, look up the forecast")

    assert turn.response_text == "Agent answer."
    assert model.offered == [(READ,)], "the agent is offered only the capabilities its profile allows"
    artifact = manager.turn_artifacts[0]
    assert [p["proposed_by"] for p in artifact.action_proposals] == ["router", "agent:notes"]
    assert sorted((e["capability_id"], e["status"]) for e in artifact.action_execution_results) == sorted(
        [(READ, "success"), ("agent-invoke-notes", "success")]
    )
    assert [run["status"] for run in artifact.delegated_runs] == ["success"]


def test_an_agent_capability_that_needs_approval_pauses_the_agent_until_yes(tmp_path):
    model = ToolModel(call=ToolCall(WRITE, {}), answer="Agent answer.")
    engine, manager = _agent_engine(
        tmp_path, model, {"notes": (["router_selected"], "none")},
        fields={"notes": {"capability_ids": [WRITE]}}, runtime=Runtime(),
    )

    asked = engine.run_text_turn("Notes, write the summary")
    resumed = engine.run_text_turn("yes")

    assert asked.response_text == "Notes wants to run tool:writer run. Reply yes to confirm."
    first = manager.turn_artifacts[0]
    assert WRITE not in [e["capability_id"] for e in first.action_execution_results]
    assert [run["status"] for run in first.delegated_runs] == ["awaiting_approval"]
    assert resumed.response_text == "Agent answer."
    second = manager.turn_artifacts[1]
    assert [record["outcome"] for record in second.approval_records] == ["approved"]
    assert [(e["capability_id"], e["status"]) for e in second.action_execution_results] == [(WRITE, "success")]
    assert [(run["mode"], run["status"]) for run in second.delegated_runs] == [("router_selected", "success")]


def test_declining_an_agent_capability_runs_nothing(tmp_path):
    engine, manager = _agent_engine(
        tmp_path, ToolModel(call=ToolCall(WRITE, {})), {"notes": (["router_selected"], "none")},
        fields={"notes": {"capability_ids": [WRITE]}}, runtime=Runtime(),
    )
    engine.run_text_turn("Notes, write the summary")

    declined = engine.run_text_turn("no")

    assert declined.response_text == "Cancelled."
    second = manager.turn_artifacts[1]
    assert [record["outcome"] for record in second.approval_records] == ["denied"]
    assert second.action_execution_results == []


def test_an_agent_cannot_run_a_capability_its_profile_does_not_allow(tmp_path):
    model = ToolModel(call=ToolCall(WRITE, {}))
    engine, manager = _agent_engine(
        tmp_path, model, {"notes": (["router_selected"], "none")},
        fields={"notes": {"capability_ids": [READ]}}, runtime=Runtime(),
    )

    turn = engine.run_text_turn("Notes, write the summary")

    artifact = manager.turn_artifacts[0]
    assert WRITE not in [e["capability_id"] for e in artifact.action_execution_results]
    assert artifact.runtime_context["agent_route"]["outcome"] == "failed"
    assert "not allowed to use" in artifact.runtime_context["agent_route"]["reason"]
    assert turn.response_text == "Grounded answer.", "the assistant answers when the agent cannot"


def test_a_panel_run_stops_when_its_agent_needs_approval(tmp_path):
    engine, manager = _agent_engine(
        tmp_path, ToolModel(call=ToolCall(WRITE, {})), {"notes": (["direct"], "none")},
        fields={"notes": {"capability_ids": [WRITE]}}, runtime=Runtime(),
    )

    result = engine.run_agent(engine.agent_registry.get("notes"), "write the summary", mode="direct")

    assert result.status == "failure"
    assert "needs your approval to run tool:writer run" in result.error
    artifact = manager.turn_artifacts[0]
    assert artifact.action_execution_results == []
    assert [p["proposed_by"] for p in artifact.action_proposals] == ["agent:notes"]

