from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from backend.app.extensions.catalog import ExtensionObservation
from backend.app.extensions.discovery import (
    DefinitionError,
    definition_fingerprint,
    parse_definition_manifest,
)
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
    observed = ExtensionObservation(**values)  # type: ignore[arg-type]
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


def test_operator_owned_definitions_expose_their_definition_for_editing(tmp_path: Path) -> None:
    config = tmp_path / "config"
    data = tmp_path / "data"
    definition_dir = data / "extensions" / "mcp"
    definition_dir.mkdir(parents=True)
    text = (
        "id: weather\nname: Weather\nversion: '1'\nenabled: false\n"
        "dependencies: [search-public-web]\nmetadata: {owner: ops}\ndefinition:\n"
        "  transport: streamable_http\n  url: https://weather.example.test/mcp\n"
    )
    (definition_dir / "weather.yaml").write_text(text, encoding="utf-8")
    manifest = parse_definition_manifest(
        "mcp", text, "data/extensions/mcp/weather.yaml", "data/extensions", "operator"
    )
    instance = ExtensionService(
        observe=lambda: ExtensionObservation(definitions=(manifest,)),
        store=ExtensionOverlayStore(db_path=tmp_path / "operator.sqlite"),
        config_dir=config,
        data_dir=data,
    )

    assert instance.read("mcp:weather").definition_available is True

    view = instance.definition("mcp:weather")
    assert view.family == "mcp"
    assert view.local_id == "weather"
    assert view.name == "Weather"
    # enabled, dependencies, and metadata must round-trip too, not just the nested
    # definition mapping - a lossy read cannot back a save that preserves the full manifest.
    assert view.enabled is False
    assert view.dependencies == ["search-public-web"]
    assert view.metadata == {"owner": "ops"}
    assert view.definition == {
        "transport": "streamable_http", "url": "https://weather.example.test/mcp",
    }
    assert view.fingerprint == definition_fingerprint(manifest)


def test_a_second_declarative_family_also_exposes_its_definition(tmp_path: Path) -> None:
    # The read contract must not be an MCP-only special case: a tool definition, the other
    # named consumer of this contract, must round-trip the same way.
    config = tmp_path / "config"
    data = tmp_path / "data"
    definition_dir = data / "extensions" / "tools"
    definition_dir.mkdir(parents=True)
    text = (
        "id: changelog-writer\nname: Changelog writer\nversion: '1'\ndefinition:\n"
        "  command: [python3, -m, scripts.changelog]\n  process:\n"
        "    subprocess: true\n    argv_allowlist: [python3]\n    env_passthrough: []\n"
        "    working_root: data\n"
    )
    (definition_dir / "changelog-writer.yaml").write_text(text, encoding="utf-8")
    manifest = parse_definition_manifest(
        "tool", text, "data/extensions/tool/changelog-writer.yaml", "data/extensions", "operator"
    )
    instance = ExtensionService(
        observe=lambda: ExtensionObservation(definitions=(manifest,)),
        store=ExtensionOverlayStore(db_path=tmp_path / "operator.sqlite"),
        config_dir=config,
        data_dir=data,
    )

    assert instance.read("tool:changelog-writer").definition_available is True
    view = instance.definition("tool:changelog-writer")
    assert view.definition["command"] == ["python3", "-m", "scripts.changelog"]


def test_a_plugin_installed_child_is_not_editable_through_this_contract(tmp_path: Path) -> None:
    # A plugin child carries the same "data/extensions" provenance as a standalone operator
    # definition (backend/app/services/extension_runtime_service.py's definitions()), but its
    # manifest lives inside the plugin bundle directory, not the flat family directory this
    # contract's discover_definition_manifests call scans - so it must never claim
    # definition_available, or a client would be told a definition exists that this reader can
    # never actually retrieve.
    config = tmp_path / "config"
    data = tmp_path / "data"
    text = "id: bundled\nname: Bundled\nversion: '1'\ndefinition:\n  transport: stdio\n"
    manifest = parse_definition_manifest(
        "mcp", text, "data/extensions/plugins/writer-bundle/bundled.yaml", "data/extensions", "external"
    )
    instance = ExtensionService(
        observe=lambda: ExtensionObservation(definitions=(manifest,)),
        store=ExtensionOverlayStore(db_path=tmp_path / "operator.sqlite"),
        config_dir=config,
        data_dir=data,
    )

    assert instance.read("mcp:bundled").definition_available is False
    with pytest.raises(ExtensionServiceError) as excinfo:
        instance.definition("mcp:bundled")
    assert excinfo.value.error == "no_definition"


def test_application_owned_definitions_have_no_editable_definition(tmp_path: Path) -> None:
    config = tmp_path / "config"
    data = tmp_path / "data"
    definition_dir = config / "extensions" / "mcp"
    definition_dir.mkdir(parents=True)
    text = "id: docs\nname: Docs\nversion: '1'\ndefinition:\n  transport: stdio\n"
    (definition_dir / "docs.yaml").write_text(text, encoding="utf-8")
    manifest = parse_definition_manifest(
        "mcp", text, "config/extensions/mcp/docs.yaml", "config/extensions", "application"
    )
    instance = ExtensionService(
        observe=lambda: ExtensionObservation(definitions=(manifest,)),
        store=ExtensionOverlayStore(db_path=tmp_path / "operator.sqlite"),
        config_dir=config,
        data_dir=data,
    )

    assert instance.read("mcp:docs").definition_available is False
    with pytest.raises(ExtensionServiceError) as excinfo:
        instance.definition("mcp:docs")
    assert excinfo.value.error == "no_definition"


def test_families_without_a_definition_contract_are_never_editable(tmp_path: Path) -> None:
    instance = service(tmp_path)

    assert instance.read("skill:notes").definition_available is False
    with pytest.raises(ExtensionServiceError) as excinfo:
        instance.definition("skill:notes")
    assert excinfo.value.error == "no_definition"


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
