from __future__ import annotations

from backend.app.actions.catalog import (
    SEARCH_PRIVATE_WEB,
    CapabilityObservation,
    build_descriptors,
)

# ADR 0005: authorization is derived from effect class by default. These are the only
# capabilities where the effect class alone cannot express why approval is still required.
_JUSTIFIED_APPROVAL_OVERRIDES = {SEARCH_PRIVATE_WEB}

_FULL_OBSERVATION = CapabilityObservation(
    search_providers=(("ddgs", True), ("searxng", True)),
    memory_service_present=True,
    memory_curation_present=True,
    provider_store_present=True,
    operator_config_present=True,
    extension_catalog_present=True,
)


def test_local_and_read_capabilities_execute_without_approval_by_default() -> None:
    for descriptor in build_descriptors(_FULL_OBSERVATION):
        if descriptor.effect_class not in ("local_read", "local_write", "external_read"):
            continue
        if descriptor.capability_id in _JUSTIFIED_APPROVAL_OVERRIDES:
            assert descriptor.authorization_rule == "requires_approval", descriptor.capability_id
        else:
            assert descriptor.authorization_rule == "allow", (
                f"{descriptor.capability_id} is a local/read effect but still requires approval"
            )


def test_operator_owned_extension_definitions_and_skills_are_allow_capabilities() -> None:
    descriptors = {d.capability_id: d for d in build_descriptors(_FULL_OBSERVATION)}
    for capability_id in (
        "extension-definition-write",
        "extension-definition-delete",
        "extension-skill-write",
        "extension-skill-delete",
        "memory-policy-update",
        "extension-state-update",
    ):
        assert descriptors[capability_id].authorization_rule == "allow", capability_id


def test_destructive_and_private_context_capabilities_still_require_approval() -> None:
    descriptors = {d.capability_id: d for d in build_descriptors(_FULL_OBSERVATION)}
    for capability_id in (
        "memory-record-forget",
        "provider-profile-delete",
        "provider-secret-rotate",
        SEARCH_PRIVATE_WEB,
    ):
        assert descriptors[capability_id].authorization_rule == "requires_approval", capability_id
