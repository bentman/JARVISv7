from __future__ import annotations

import pytest
from backend.app.extensions.contracts import (
    ExtensionCatalog,
    ExtensionDescriptor,
    ExtensionError,
)
from backend.app.extensions.discovery import parse_definition_manifest
from backend.app.extensions.lifecycle import (
    HookDefinition,
    PluginDefinition,
    validate_plugin_transition,
)


def descriptor(**overrides) -> ExtensionDescriptor:
    values = {
        "extension_id": "prompt:daily-review",
        "family": "prompt",
        "local_id": "daily-review",
        "version": "1",
        "display_name": "Daily review",
        "source": "config/prompts/daily-review.yaml",
        "provenance": "config/prompts",
        "trust": "application",
        "state": "enabled",
        "readiness": "ready",
        "availability": "available",
    }
    values.update(overrides)
    return ExtensionDescriptor(**values)  # type: ignore[arg-type]


def test_extension_id_must_name_its_family_and_local_id() -> None:
    with pytest.raises(ExtensionError, match="extension_id must be"):
        descriptor(extension_id="daily-review")


def test_local_id_must_be_safe() -> None:
    with pytest.raises(ExtensionError, match="local_id must match"):
        descriptor(extension_id="prompt:../etc", local_id="../etc")


def test_an_unavailable_extension_must_explain_itself() -> None:
    with pytest.raises(ValueError, match="unavailable_explanation must be a non-empty string"):
        descriptor(availability="disabled")

    assert descriptor(availability="disabled", unavailable_explanation="Turned off.").state == "enabled"


def test_an_extension_cannot_declare_itself_trusted_through_metadata() -> None:
    with pytest.raises(ValueError, match="metadata claims must remain untrusted"):
        descriptor(metadata_claims={"requested": {"trusted": True}})


def test_catalog_rejects_duplicate_extension_ids() -> None:
    catalog = ExtensionCatalog()
    catalog.register(descriptor())

    with pytest.raises(ExtensionError, match="extension already registered"):
        catalog.register(descriptor())


def test_catalog_snapshot_is_sorted_and_families_are_counted() -> None:
    catalog = ExtensionCatalog()
    catalog.register(descriptor())
    catalog.register(descriptor(extension_id="skill:notes", family="skill", local_id="notes", trust="external"))

    assert [row["extension_id"] for row in catalog.snapshot()] == ["prompt:daily-review", "skill:notes"]
    assert catalog.families() == {"prompt": 1, "skill": 1}


def test_hooks_and_plugins_cannot_register_without_a_definition() -> None:
    catalog = ExtensionCatalog()

    with pytest.raises(ExtensionError, match="must declare a definition"):
        catalog.register(
            descriptor(extension_id="hook:audit", family="hook", local_id="audit")
        )

    catalog.register(
        descriptor(
            extension_id="hook:audit",
            family="hook",
            local_id="audit",
            definition=HookDefinition("audit", "turn_persisted", "local_read").to_dict(),
        )
    )
    assert catalog.get("hook:audit") is not None


def test_a_hook_with_side_effects_must_invoke_a_capability() -> None:
    assert HookDefinition("reader", "turn_persisted", "local_read").capability_id is None

    with pytest.raises(ExtensionError, match="must invoke a governed capability"):
        HookDefinition("writer", "turn_persisted", "local_write")

    assert HookDefinition("writer", "turn_persisted", "local_write", "memory-record-confirm")


def test_hook_events_are_closed() -> None:
    with pytest.raises(ExtensionError, match="hook event must be one of"):
        HookDefinition("h", "whenever_i_like", "local_read")


def test_plugin_lifecycle_transitions_are_enforced() -> None:
    validate_plugin_transition("installed", "enabled")
    validate_plugin_transition("enabled", "retired")

    with pytest.raises(ExtensionError, match="cannot move from retired to enabled"):
        validate_plugin_transition("retired", "enabled")

    with pytest.raises(ExtensionError, match="plugin state must be one of"):
        PluginDefinition("p", "1", "running")


def test_a_plugin_only_names_the_extensions_it_contains() -> None:
    definition = PluginDefinition("bundle", "1", "installed", ("skill:notes", "prompt:daily-review"))

    payload = definition.to_dict()

    assert payload["contained_extension_ids"] == ["skill:notes", "prompt:daily-review"]
    # Packaging names its contents; it grants them nothing.
    assert "trust" not in payload and "authority" not in payload


def test_new_definition_families_require_a_definition() -> None:
    with pytest.raises(ExtensionError, match="must declare a definition"):
        ExtensionCatalog().register(
            descriptor(extension_id="mcp:public", family="mcp", local_id="public")
        )


def test_definition_manifests_record_untrusted_metadata() -> None:
    manifest = parse_definition_manifest(
        "mcp",
        "id: public\nname: Public\nversion: '1'\ndefinition:\n  transport: stdio\nmetadata:\n  label: built-in\n",
        "config/extensions/mcp/public.yaml",
        "config/extensions",
        "application",
    )

    assert manifest.metadata_claims["declaration"]["trusted"] is False


def test_definition_manifests_allow_a_secret_reference_but_not_a_secret() -> None:
    manifest = parse_definition_manifest(
        "mcp",
        "id: remote\nname: Remote\nversion: '1'\ndefinition:\n  credential_ref: operator-mcp\n",
        "config/extensions/mcp/remote.yaml",
        "config/extensions",
        "application",
    )

    assert manifest.definition["credential_ref"] == "operator-mcp"

    with pytest.raises(ValueError, match="secret-bearing field"):
        parse_definition_manifest(
            "mcp",
            "id: bad\nname: Bad\nversion: '1'\ndefinition:\n  token: value\n",
            "config/extensions/mcp/bad.yaml",
            "config/extensions",
            "application",
        )
