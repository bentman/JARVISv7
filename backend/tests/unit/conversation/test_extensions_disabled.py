from __future__ import annotations

from pathlib import Path

import pytest
from backend.app.extensions.catalog import ExtensionObservation
from backend.app.extensions.prompts import list_prompt_templates_with_errors
from backend.app.extensions.skills import list_skills_with_errors
from backend.app.extensions.store import ExtensionOverlayStore
from backend.app.services.extension_service import ExtensionService
from backend.tests.unit.conversation.test_search_turn import engine_at, governed_engine_at

pytestmark = [pytest.mark.turn]


def _service(tmp_path: Path, observation: ExtensionObservation) -> ExtensionService:
    return ExtensionService(
        observe=lambda: observation,
        store=ExtensionOverlayStore(db_path=tmp_path / "operator.sqlite"),
        config_dir=tmp_path,
        data_dir=tmp_path,
    )


def test_an_empty_extension_estate_is_not_an_error(tmp_path: Path) -> None:
    # No config/prompts, no skills root, no families observed at all.
    service = _service(tmp_path, ExtensionObservation())

    catalog = service.catalog()

    assert catalog.extensions == []
    assert catalog.families == {}
    assert service.errors().errors == []
    assert list_prompt_templates_with_errors(tmp_path).templates == []
    assert list_skills_with_errors(tmp_path).skills == []


def test_a_text_turn_still_completes_with_every_extension_disabled(tmp_path: Path) -> None:
    engine, manager = engine_at(tmp_path)

    turn = engine.run_text_turn("Hello there")

    assert turn.failure_reason is None
    assert turn.response_text
    assert manager.turn_artifacts[0].search is None


def test_a_search_turn_still_completes_with_every_extension_disabled(tmp_path: Path) -> None:
    engine, manager = engine_at(tmp_path)

    turn = engine.run_text_turn("Please search for a public topic")

    assert turn.failure_reason is None
    assert "[S1]" in turn.response_text
    assert manager.turn_artifacts[0].tools_invoked == ["ddgs"]


def test_disabling_every_extension_does_not_touch_the_turn_path(tmp_path: Path) -> None:
    service = _service(
        tmp_path,
        ExtensionObservation(
            search_providers=(("ddgs", True),),
            personalities=(("default", "Morgan", True, "config/personality/default.yaml"),),
        ),
    )
    for extension_id in ("search_provider:ddgs", "personality:default"):
        service.set_state(
            extension_id=extension_id, state="disabled", expected_revision=None, reason="off"
        )
    assert all(item.state == "disabled" for item in service.catalog().extensions)

    # The catalog records operator intent; it is not consulted to decide whether a turn runs.
    engine, manager = governed_engine_at(tmp_path / "turns")
    turn = engine.run_text_turn("Please search for a public topic")

    assert turn.failure_reason is None
    assert "[S1]" in turn.response_text
    assert manager.turn_artifacts[0].action_execution_results[0]["status"] == "success"


def test_a_missing_skills_root_never_reaches_the_turn_path(tmp_path: Path) -> None:
    assert not (tmp_path / "extensions" / "skills").exists()

    engine, _ = engine_at(tmp_path / "turns")
    turn = engine.run_text_turn("Hello there")

    assert turn.failure_reason is None
