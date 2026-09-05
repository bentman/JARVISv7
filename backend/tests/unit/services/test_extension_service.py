from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from backend.app.extensions.catalog import ExtensionObservation
from backend.app.extensions.discovery import DefinitionError
from backend.app.extensions.prompts import list_prompt_templates_with_errors
from backend.app.extensions.skills import list_skills_with_errors
from backend.app.extensions.store import ExtensionOverlayStore
from backend.app.services.extension_service import (
    ExtensionService,
    ExtensionServiceError,
    observe_extensions,
)


def seed(tmp_path: Path) -> None:
    skill = tmp_path / "extensions" / "skills" / "notes"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text(
        "---\nname: Notes\ndescription: d\nversion: '2'\nrequested_tools: [search-public-web]\n---\nThe body.",
        encoding="utf-8",
    )
    prompts = tmp_path / "prompts"
    prompts.mkdir(exist_ok=True)
    (prompts / "review.yaml").write_text(
        "prompt_id: review\nversion: '1'\ntitle: R\ndescription: d\nauthority: user\nbody: hello\n",
        encoding="utf-8",
    )


def service(tmp_path: Path, **observation) -> ExtensionService:
    seed(tmp_path)
    values = {
        "prompts": tuple(list_prompt_templates_with_errors(tmp_path).templates),
        "skills": tuple(list_skills_with_errors(tmp_path).skills),
        "search_providers": (("ddgs", True), ("searxng", False)),
    }
    values.update(observation)
    observed = ExtensionObservation(**values)
    return ExtensionService(
        observe=lambda: observed,
        store=ExtensionOverlayStore(db_path=tmp_path / "operator.sqlite"),
        config_dir=tmp_path,
        data_dir=tmp_path,
    )


def test_the_catalog_reports_every_observed_family(tmp_path: Path) -> None:
    catalog = service(tmp_path).catalog()

    assert catalog.families == {"prompt": 1, "search_provider": 2, "skill": 1}
    assert [item.extension_id for item in catalog.extensions] == [
        "prompt:review", "search_provider:ddgs", "search_provider:searxng", "skill:notes",
    ]


def test_an_operator_decision_survives_a_refresh(tmp_path: Path) -> None:
    instance = service(tmp_path)

    instance.set_state(
        extension_id="skill:notes", state="disabled", expected_revision=None, reason="not vetted"
    )
    instance.refresh()

    assert instance.read("skill:notes").state == "disabled"
    assert instance.catalog().extensions[-1].state == "disabled"


def test_a_stale_revision_conflicts_with_the_current_one(tmp_path: Path) -> None:
    instance = service(tmp_path)
    instance.set_state(extension_id="skill:notes", state="disabled", expected_revision=None, reason=None)

    with pytest.raises(ExtensionServiceError) as excinfo:
        instance.set_state(extension_id="skill:notes", state="enabled", expected_revision=99, reason=None)

    assert excinfo.value.status_code == 409
    assert excinfo.value.detail()["current_revision"] == 1


def test_a_retired_extension_cannot_be_revived(tmp_path: Path) -> None:
    instance = service(tmp_path)
    instance.set_state(extension_id="skill:notes", state="retired", expected_revision=None, reason="gone")

    with pytest.raises(ExtensionServiceError) as excinfo:
        instance.set_state(extension_id="skill:notes", state="enabled", expected_revision=1, reason=None)

    assert excinfo.value.status_code == 422
    assert "retired" in excinfo.value.message


def test_bodies_are_disclosed_only_on_request_and_only_where_they_exist(tmp_path: Path) -> None:
    instance = service(tmp_path)

    assert instance.body("skill:notes").body.strip() == "The body."
    assert instance.body("prompt:review").body.strip() == "hello"

    with pytest.raises(ExtensionServiceError) as excinfo:
        instance.body("search_provider:ddgs")
    assert excinfo.value.error == "no_body"


def test_requested_tools_reach_the_view_as_an_untrusted_request(tmp_path: Path) -> None:
    view = service(tmp_path).read("skill:notes")

    assert view.dependencies == ["search-public-web"]
    assert view.metadata_claims["requested_capabilities"]["trusted"] is False
    assert view.trust == "external"


def test_unknown_extensions_are_reported_not_guessed(tmp_path: Path) -> None:
    with pytest.raises(ExtensionServiceError) as excinfo:
        service(tmp_path).read("skill:does-not-exist")

    assert excinfo.value.status_code == 404


def test_load_errors_are_surfaced_without_breaking_the_catalog(tmp_path: Path) -> None:
    seed(tmp_path)
    (tmp_path / "prompts" / "broken.yaml").write_text(
        "prompt_id: broken\nversion: '1'\ntitle: B\ndescription: d\nauthority: application\nbody: x\n",
        encoding="utf-8",
    )
    instance = service(tmp_path, prompt_errors=tuple(list_prompt_templates_with_errors(tmp_path).errors))

    errors = instance.errors().errors

    assert [error.source for error in errors] == ["broken.yaml"]
    assert instance.catalog().families["prompt"] >= 1


def test_a_corrupt_overlay_degrades_instead_of_raising(tmp_path: Path) -> None:
    seed(tmp_path)
    corrupt = tmp_path / "operator.sqlite"
    corrupt.write_text("this is not a database", encoding="utf-8")
    store = ExtensionOverlayStore(db_path=corrupt)

    instance = ExtensionService(
        observe=lambda: ExtensionObservation(search_providers=(("ddgs", True),)),
        store=store,
        config_dir=tmp_path,
        data_dir=tmp_path,
    )

    assert store.available() is False
    assert instance.catalog().families == {"search_provider": 1}


def test_definition_load_errors_are_exposed_without_breaking_other_families(tmp_path: Path) -> None:
    instance = service(
        tmp_path,
        definition_errors=(DefinitionError("mcp", "data/extensions/mcp/bad.yaml", "bad yaml"),),
    )

    assert [(item.family, item.source, item.reason) for item in instance.errors().errors] == [
        ("mcp", "data/extensions/mcp/bad.yaml", "bad yaml"),
    ]


def test_observation_discovers_application_definitions(tmp_path: Path) -> None:
    config = tmp_path / "config"
    data = tmp_path / "data"
    definition = config / "extensions" / "mcp" / "docs.yaml"
    definition.parent.mkdir(parents=True)
    definition.write_text(
        "id: docs\nname: Docs\nversion: '1'\ndefinition:\n  transport: stdio\n",
        encoding="utf-8",
    )

    observed = observe_extensions(
        settings_provider=lambda: SimpleNamespace(),
        personality_provider=lambda: SimpleNamespace(profiles=[], errors=[]),
        config_dir=config,
        data_dir=data,
    )

    assert [(item.local_id, item.provenance) for item in observed.definitions] == [
        ("docs", "config/extensions"),
    ]
