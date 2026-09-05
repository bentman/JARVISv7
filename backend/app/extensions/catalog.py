from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from backend.app.extensions.contracts import (
    ExtensionDescriptor,
    extension_id,
)
from backend.app.extensions.prompts import PromptTemplate, PromptTemplateError
from backend.app.extensions.skills import SkillError, SkillManifest

SEARCH_DISABLED = (
    "No web search provider is enabled. Enable DDGS, SearXNG, or Tavily in operator configuration."
)
PERSONALITY_DISABLED = "This personality profile declares enabled: false and cannot be selected."
PROVIDER_LOCKED = "The provider secret store is locked; complete or roll back the key rotation."
SKILL_SCRIPTS_DISABLED = (
    "This skill declares scripts. Script execution requires a privileged_execution capability, "
    "and none is registered."
)
CAPABILITY_UNAVAILABLE = "This capability is not currently available."


@dataclass(frozen=True, slots=True)
class ObservedRecord:
    local_id: str
    display_name: str
    version: str = "0"
    source: str = "builtin"
    provenance: str = "application"
    trust: str = "application"
    declared_enabled: bool = True
    readiness: str = "ready"
    availability: str = "available"
    unavailable_explanation: str = ""
    dependencies: tuple[str, ...] = ()
    metadata_claims: dict[str, Any] = field(default_factory=dict)
    definition: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtensionObservation:
    settings: tuple[tuple[str, str], ...] = ()
    personalities: tuple[tuple[str, str, bool, str], ...] = ()
    personality_errors: tuple[tuple[str, str], ...] = ()
    providers: tuple[tuple[str, str, str, bool], ...] = ()
    provider_store_locked: bool = False
    search_providers: tuple[tuple[str, bool], ...] = ()
    prompts: tuple[PromptTemplate, ...] = ()
    prompt_errors: tuple[PromptTemplateError, ...] = ()
    skills: tuple[SkillManifest, ...] = ()
    skill_errors: tuple[SkillError, ...] = ()
    capabilities: tuple[tuple[str, str, str], ...] = ()


def build_extension_descriptors(
    observation: ExtensionObservation,
    overlay: dict[str, tuple[str, str | None]] | None = None,
) -> tuple[ExtensionDescriptor, ...]:
    overlay = overlay or {}
    records: list[tuple[str, ObservedRecord]] = []
    records += [("setting", record) for record in _settings(observation)]
    records += [("personality", record) for record in _personalities(observation)]
    records += [("provider", record) for record in _providers(observation)]
    records += [("search_provider", record) for record in _search_providers(observation)]
    records += [("prompt", record) for record in _prompts(observation)]
    records += [("skill", record) for record in _skills(observation)]
    records += [("capability", record) for record in _capabilities(observation)]

    collisions = _collisions(records)
    descriptors: list[ExtensionDescriptor] = []
    seen: set[str] = set()
    for family, record in records:
        identifier = extension_id(family, record.local_id)
        if identifier in seen:
            continue
        seen.add(identifier)
        state, availability, explanation = _state(identifier, record, overlay)
        descriptors.append(
            ExtensionDescriptor(
                extension_id=identifier,
                family=family,  # type: ignore[arg-type]
                local_id=record.local_id,
                version=record.version,
                display_name=record.display_name,
                source=record.source,
                provenance=record.provenance,
                trust=record.trust,  # type: ignore[arg-type]
                state=state,  # type: ignore[arg-type]
                readiness=record.readiness,  # type: ignore[arg-type]
                availability=availability,  # type: ignore[arg-type]
                unavailable_explanation=explanation,
                dependencies=record.dependencies,
                collisions=collisions.get(identifier, ()),
                metadata_claims=record.metadata_claims,
                definition=record.definition,
            )
        )
    descriptors.sort(key=lambda item: item.extension_id)
    return tuple(descriptors)


def _state(
    identifier: str, record: ObservedRecord, overlay: dict[str, tuple[str, str | None]]
) -> tuple[str, str, str]:
    """Overlay wins, then the family's declared enablement, then enabled."""
    availability, explanation = record.availability, record.unavailable_explanation
    operator_state = overlay.get(identifier, (None, None))[0]
    if operator_state in {"disabled", "retired"}:
        return operator_state, "disabled", f"An operator set this extension to {operator_state}."
    if not record.declared_enabled:
        return "disabled", "disabled", explanation or "This extension declares itself disabled."
    return "enabled", availability, explanation


def _collisions(records: list[tuple[str, ObservedRecord]]) -> dict[str, tuple[str, ...]]:
    counts = Counter(extension_id(family, record.local_id) for family, record in records)
    return {
        identifier: (f"{count} entries share this identifier",)
        for identifier, count in counts.items()
        if count > 1
    }


def _settings(observation: ExtensionObservation) -> list[ObservedRecord]:
    return [
        ObservedRecord(
            local_id=key.lower().replace("_", "-"),
            display_name=key,
            source="backend/app/services/operator_config_service.py",
            provenance="application",
            metadata_claims={"classification": {"tier": tier, "trusted": False}},
        )
        for key, tier in observation.settings
    ]


def _personalities(observation: ExtensionObservation) -> list[ObservedRecord]:
    return [
        ObservedRecord(
            local_id=profile_id,
            display_name=display_name,
            source=source,
            provenance="config/personality",
            declared_enabled=enabled,
            unavailable_explanation="" if enabled else PERSONALITY_DISABLED,
        )
        for profile_id, display_name, enabled, source in observation.personalities
    ]


def _providers(observation: ExtensionObservation) -> list[ObservedRecord]:
    locked = observation.provider_store_locked
    records = []
    for profile_id, name, readiness_state, builtin in observation.providers:
        degraded = readiness_state == "credential_required"
        records.append(
            ObservedRecord(
                local_id=profile_id.replace(":", "-"),
                display_name=name,
                source="data/operator.sqlite" if not builtin else "builtin",
                provenance="application" if builtin else "operator",
                trust="application" if builtin else "operator",
                readiness="degraded" if degraded or locked else "ready",
                availability="misconfigured" if locked else "available",
                unavailable_explanation=PROVIDER_LOCKED if locked else "",
            )
        )
    return records


def _search_providers(observation: ExtensionObservation) -> list[ObservedRecord]:
    return [
        ObservedRecord(
            local_id=name,
            display_name=name,
            source="backend/app/runtimes/internetsearch",
            provenance="application",
            declared_enabled=available,
            readiness="ready" if available else "unavailable",
            availability="available" if available else "disabled",
            unavailable_explanation="" if available else SEARCH_DISABLED,
        )
        for name, available in observation.search_providers
    ]


def _prompts(observation: ExtensionObservation) -> list[ObservedRecord]:
    return [
        ObservedRecord(
            local_id=template.prompt_id,
            display_name=template.title,
            version=template.version,
            source=f"config/prompts/{template.prompt_id}.yaml",
            provenance="config/prompts",
            metadata_claims={
                "template": {
                    "authority": template.authority,
                    "variables": list(template.variables),
                    "trusted": False,
                }
            },
        )
        for template in observation.prompts
    ]


def _skills(observation: ExtensionObservation) -> list[ObservedRecord]:
    return [
        ObservedRecord(
            local_id=skill.skill_id,
            display_name=skill.name,
            version=skill.version,
            source=skill.source,
            provenance="data/extensions/skills",
            trust="external",
            readiness="degraded" if skill.has_scripts else "ready",
            availability="disabled" if skill.has_scripts else "available",
            unavailable_explanation=SKILL_SCRIPTS_DISABLED if skill.has_scripts else "",
            dependencies=skill.requested_tools,
            metadata_claims=skill.metadata_claims(),
        )
        for skill in observation.skills
    ]


def _capabilities(observation: ExtensionObservation) -> list[ObservedRecord]:
    return [
        ObservedRecord(
            local_id=capability_id,
            display_name=capability_id,
            source="backend/app/actions/catalog.py",
            provenance="application",
            readiness=readiness,
            availability=availability,
            unavailable_explanation="" if availability == "available" else CAPABILITY_UNAVAILABLE,
        )
        for capability_id, readiness, availability in observation.capabilities
    ]
