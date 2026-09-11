from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
from backend.app.extensions.discovery import DefinitionManifest
from backend.app.extensions.hooks import HookRunner


@dataclass
class ProposalView:
    capability_id: str
    status: str = "awaiting_approval"


class Actions:
    def __init__(self, effects: dict[str, str]) -> None:
        self.effects = effects
        self.proposals: list[dict[str, Any]] = []
        self.on_propose = None

    def descriptor(self, capability_id: str) -> object | None:
        effect = self.effects.get(capability_id)
        return SimpleNamespace(effect_class=effect) if effect else None

    def propose(self, **kwargs: Any) -> ProposalView:
        self.proposals.append(kwargs)
        if self.on_propose is not None:
            self.on_propose()
        return ProposalView(kwargs["capability_id"])


def hook(
    local_id: str,
    definition: dict[str, Any],
    *,
    trust: str = "application",
    enabled: bool = True,
) -> DefinitionManifest:
    return DefinitionManifest(
        family="hook", local_id=local_id, display_name=local_id, version="1",
        source=f"config/extensions/hooks/{local_id}.yaml", provenance="config/extensions",
        trust=trust, declared_enabled=enabled, definition=definition,
    )


def _runner(
    definitions: list[DefinitionManifest], actions: Actions, monkeypatch: pytest.MonkeyPatch
) -> tuple[HookRunner, list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    import backend.app.extensions.hooks as hooks

    monkeypatch.setattr(hooks, "append_action_event", lambda entry: evidence.append(entry))
    return HookRunner(actions, lambda: definitions), evidence  # type: ignore[arg-type]


def test_closed_event_names_are_refused_without_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, evidence = _runner([], Actions({}), monkeypatch)

    with pytest.raises(ValueError, match="unknown hook event"):
        runner.emit("model_finished", {"session_id": "s"})

    assert evidence == []


def test_application_record_event_hooks_are_observed_in_stable_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    definitions = [
        hook("z-last", {"event": "session_started", "handler": "record_event"}),
        hook("a-first", {"event": "session_started", "handler": "record_event"}),
    ]
    runner, evidence = _runner(definitions, Actions({}), monkeypatch)

    result = runner.emit("session_started", {"session_id": "s-1"})

    assert [(item["hook_id"], item["status"]) for item in result] == [
        ("a-first", "observed"), ("z-last", "observed"),
    ]
    assert [entry["record"]["hook_id"] for entry in evidence] == ["a-first", "z-last"]


def test_untrusted_inline_hook_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    runner, evidence = _runner(
        [hook("external", {"event": "session_started", "handler": "record_event"}, trust="external")],
        Actions({}),
        monkeypatch,
    )

    result = runner.emit("session_started", {})

    assert result == [{"hook_id": "external", "event": "session_started", "status": "failure"}]
    assert evidence[0]["record"]["status"] == "failure"


def test_effectful_hook_only_parks_a_governed_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    actions = Actions({"external-read": "external_read"})
    runner, _ = _runner(
        [hook("research", {
            "event": "turn_admitted", "effect_class": "external_read",
            "capability_id": "external-read", "arguments": {"topic": "weather"},
        })],
        actions,
        monkeypatch,
    )

    result = runner.emit("turn_admitted", {"session_id": "s-1", "turn_id": "t-1"})

    assert actions.proposals == [{
        "capability_id": "external-read", "arguments": {"topic": "weather"},
        "proposed_by": "hook:research", "reason": "Lifecycle event: turn_admitted",
        "session_id": "s-1", "turn_id": "t-1", "caller": "hook",
    }]
    assert result[0]["action"]["status"] == "awaiting_approval"


def test_effect_mismatch_is_refused_before_a_proposal(monkeypatch: pytest.MonkeyPatch) -> None:
    actions = Actions({"write": "local_write"})
    runner, _ = _runner(
        [hook("bad", {
            "event": "session_closed", "effect_class": "external_read", "capability_id": "write",
        })],
        actions,
        monkeypatch,
    )

    result = runner.emit("session_closed", {})

    assert result[0]["status"] == "failure"
    assert actions.proposals == []


def test_hook_emission_does_not_recurse(monkeypatch: pytest.MonkeyPatch) -> None:
    actions = Actions({"read": "local_read"})
    runner, _ = _runner(
        [hook("once", {
            "event": "session_started", "effect_class": "local_read", "capability_id": "read",
        })],
        actions,
        monkeypatch,
    )
    nested: list[dict[str, Any]] = []
    actions.on_propose = lambda: nested.extend(runner.emit("session_started", {}))

    result = runner.emit("session_started", {})

    assert len(result) == 1
    assert nested == []
    assert len(actions.proposals) == 1
