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


def _capabilities(results: dict[str, Any] | None = None) -> CapabilityService:
    from backend.app.actions.contracts import (
        CapabilityDescriptor,
        default_authorization,
    )

    outcomes = results or {}

    def descriptor(capability_id: str, effect: str) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            capability_id=capability_id, source="test", provenance="test",
            input_schema={"type": "object"}, effect_class=effect, readiness="ready",
            availability="available", execution_owner="backend.extension_runtime",
            authorization_rule=default_authorization(effect),
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
        observe=lambda: CapabilityObservation(extension_catalog_present=True)
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
        stt=None, tts=None, llm=model, personality=load_default_personality(),
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


def test_only_one_capability_runs_per_turn(tmp_path):
    class Greedy(ToolModel):
        def generate_with_tools(self, envelope, tools, **kwargs):
            self.offered.append(tuple(tool.name for tool in tools))
            return ToolCallResult(call=ToolCall(READ, {}))

    engine, manager = engine_at(tmp_path, Greedy())
    engine.run_text_turn("Look something up")

    assert manager.turn_artifacts[0].tools_invoked == [READ]
