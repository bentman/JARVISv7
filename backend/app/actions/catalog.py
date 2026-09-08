from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.actions.contracts import (
    CapabilityDescriptor,
    EffectClass,
    default_authorization,
)

SEARCH_PUBLIC_WEB = "search-public-web"
SEARCH_PRIVATE_WEB = "search-private-web"
MEMORY_RECORD_CONFIRM = "memory-record-confirm"
MEMORY_RECORD_DISPUTE = "memory-record-dispute"
MEMORY_RECORD_CORRECT = "memory-record-correct"
MEMORY_RECORD_FORGET = "memory-record-forget"
MEMORY_POLICY_UPDATE = "memory-policy-update"
PROVIDER_PROFILE_WRITE = "provider-profile-write"
PROVIDER_PROFILE_DELETE = "provider-profile-delete"
PROVIDER_SELECTION_UPDATE = "provider-selection-update"
PROVIDER_SECRET_ROTATE = "provider-secret-rotate"
PROVIDER_CONNECTIVITY_TEST = "provider-connectivity-test"
OPERATOR_CONFIG_WRITE = "operator-config-write"
EXTENSION_STATE_UPDATE = "extension-state-update"
EXTENSION_DEFINITION_WRITE = "extension-definition-write"
EXTENSION_DEFINITION_DELETE = "extension-definition-delete"
EXTENSION_SKILL_WRITE = "extension-skill-write"
EXTENSION_SKILL_DELETE = "extension-skill-delete"

SEARCH_UNAVAILABLE = (
    "No web search provider is enabled. Enable DDGS, SearXNG, or Tavily in operator configuration."
)
MEMORY_UNAVAILABLE = "Memory service is unavailable, so memory lifecycle actions cannot run."
PROVIDER_LOCKED = "The provider secret store is locked; complete or roll back the key rotation."
PROVIDER_STORE_UNAVAILABLE = "Provider profile storage is unavailable."
EXTENSION_CATALOG_UNAVAILABLE = "The extension catalog is unavailable."
OPERATOR_CONFIG_UNAVAILABLE = (
    "The .env file is missing; copy .env.example to .env before changing operator configuration."
)

SEARCH_TIMEOUT_MS = 30_000
MEMORY_TIMEOUT_MS = 10_000
PROVIDER_TIMEOUT_MS = 15_000
CONFIG_TIMEOUT_MS = 5_000
RESULT_BYTES = 16_000

_REVISION = {"type": "integer", "minimum": 1}
_REASON = {"type": "string", "maxLength": 256}
_FACT_ID = {"type": "string", "minLength": 1, "maxLength": 128}
_PROFILE_ID = {"type": "string", "minLength": 1, "maxLength": 128}


@dataclass(frozen=True, slots=True)
class ProviderObservation:
    profile_id: str
    kind: str
    readiness_state: str
    cloud_eligible: bool
    builtin: bool


@dataclass(frozen=True, slots=True)
class CapabilityObservation:
    search_providers: tuple[tuple[str, bool], ...] = ()
    memory_service_present: bool = False
    memory_curation_present: bool = False
    provider_store_present: bool = False
    provider_store_locked: bool = False
    providers: tuple[ProviderObservation, ...] = ()
    operator_config_present: bool = False
    operator_config_keys: tuple[str, ...] = ()
    extension_catalog_present: bool = False
    agents: tuple[tuple[str, str, str, str, str, int, bool, str], ...] = ()
    agent_errors: tuple[tuple[str, str], ...] = ()

    @property
    def enabled_search_providers(self) -> tuple[str, ...]:
        return tuple(name for name, available in self.search_providers if available)


def build_descriptors(observation: CapabilityObservation) -> tuple[CapabilityDescriptor, ...]:
    return (
        *_search(observation),
        *_memory(observation),
        *_provider(observation),
        _operator(observation),
        _extension(observation),
        *_extension_definitions(observation),
        *_agents(observation),
    )


def _search(observation: CapabilityObservation) -> tuple[CapabilityDescriptor, ...]:
    enabled = observation.enabled_search_providers
    availability = "available" if enabled else "disabled"
    readiness = "ready" if len(enabled) >= 2 else "degraded" if enabled else "unavailable"
    schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["search", "research"]},
            "topic": {"type": "string", "minLength": 1, "maxLength": 240},
            "queries": {
                "type": "array",
                "minItems": 1,
                "maxItems": 3,
                "items": {"type": "string", "minLength": 1, "maxLength": 240},
            },
        },
        "required": ["mode", "topic", "queries"],
        "additionalProperties": False,
    }
    result_schema = {
        "type": "object",
        "properties": {
            "outcome": {"type": "string"},
            "mode": {"type": "string"},
            "source_count": {"type": "integer"},
            "attempt_count": {"type": "integer"},
            "limitations": {"type": "array", "items": {"type": "string"}},
        },
    }
    common: dict[str, Any] = {
        "source": "builtin",
        "provenance": "backend.app.services.search_service",
        "input_schema": schema,
        "effect_class": "external_read",
        "readiness": readiness,
        "availability": availability,
        "execution_owner": "backend.app.services.search_service.SearchService",
        "timeout_policy": {"timeout_ms": SEARCH_TIMEOUT_MS},
        "cancellation_policy": {"cancellable": True, "owner": "SearchOperation"},
        "result_schema": result_schema,
        "unavailable_explanation": "" if enabled else SEARCH_UNAVAILABLE,
        "approval_mode": "turn_boundary",
        "metadata_claims": {"providers": {"enabled": list(enabled), "trusted": False}},
    }
    return (
        CapabilityDescriptor(
            capability_id=SEARCH_PUBLIC_WEB,
            authorization_rule=default_authorization(common["effect_class"]),
            artifact_evidence={
                "records": ["action_proposals", "authorization_decisions", "action_execution_results"]
            },
            **common,
        ),
        CapabilityDescriptor(
            capability_id=SEARCH_PRIVATE_WEB,
            # An outbound read alone does not need approval, but a private query carries the
            # user's own context off the machine, which the effect class cannot express.
            authorization_rule="requires_approval",
            artifact_evidence={
                "records": [
                    "action_proposals",
                    "authorization_decisions",
                    "approval_records",
                    "action_execution_results",
                    "action_cancellations",
                ]
            },
            **common,
        ),
    )


def _memory(observation: CapabilityObservation) -> tuple[CapabilityDescriptor, ...]:
    present = observation.memory_service_present
    availability = "available" if present else "disabled"
    readiness = (
        "ready" if present and observation.memory_curation_present
        else "degraded" if present
        else "unavailable"
    )
    lifecycle_schema = {
        "type": "object",
        "properties": {"fact_id": _FACT_ID, "expected_revision": _REVISION, "reason": _REASON},
        "required": ["fact_id", "expected_revision"],
        "additionalProperties": False,
    }
    common: dict[str, Any] = {
        "source": "builtin",
        "provenance": "backend.app.services.memory_service",
        "readiness": readiness,
        "availability": availability,
        "execution_owner": "backend.app.services.memory_service.MemoryService",
        "timeout_policy": {"timeout_ms": MEMORY_TIMEOUT_MS},
        "cancellation_policy": {"cancellable": False, "owner": "MemoryService"},
        "result_schema": {"type": "object"},
        "unavailable_explanation": "" if present else MEMORY_UNAVAILABLE,
        "approval_mode": "same_turn",
    }
    lifecycle: dict[str, Any] = {**common, "input_schema": lifecycle_schema}
    return (
        _capability(MEMORY_RECORD_CONFIRM, "local_write", **lifecycle),
        _capability(MEMORY_RECORD_DISPUTE, "local_write", **lifecycle),
        _capability(
            MEMORY_RECORD_CORRECT,
            "local_write",
            **{
                **common,
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "fact_id": _FACT_ID,
                        "expected_revision": _REVISION,
                        "replacement_text": {"type": "string", "minLength": 1, "maxLength": 1024},
                        "replacement_value": {"type": "string", "maxLength": 1024},
                        "reason": _REASON,
                    },
                    "required": ["fact_id", "expected_revision", "replacement_text"],
                    "additionalProperties": False,
                },
            },
        ),
        _capability(
            MEMORY_RECORD_FORGET,
            "destructive_action",
            **{
                **lifecycle,
                "cancellation_policy": {"cancellable": True, "owner": "MemoryService"},
                "boundaries": _boundaries(MEMORY_TIMEOUT_MS, cancellable=True),
            },
        ),
        _capability(
            MEMORY_POLICY_UPDATE,
            "local_write",
            **{
                **common,
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "automatic_curation_enabled": {"type": "boolean"},
                        "expected_revision": _REVISION,
                    },
                    "required": ["automatic_curation_enabled", "expected_revision"],
                    "additionalProperties": False,
                },
            },
        ),
    )


def _provider(observation: CapabilityObservation) -> tuple[CapabilityDescriptor, ...]:
    present = observation.provider_store_present
    locked = observation.provider_store_locked
    availability = "available" if present and not locked else "misconfigured" if locked else "disabled"
    explanation = "" if availability == "available" else (
        PROVIDER_LOCKED if locked else PROVIDER_STORE_UNAVAILABLE
    )
    degraded = any(
        provider.readiness_state == "credential_required" for provider in observation.providers
    )
    readiness = "unavailable" if not present else "degraded" if degraded or locked else "ready"
    profile_write_schema = {
        "type": "object",
        "properties": {
            "profile_id": _PROFILE_ID,
            "name": {"type": "string", "minLength": 1, "maxLength": 80},
            "kind": {"type": "string", "maxLength": 40},
            "endpoint": {"type": ["string", "null"], "maxLength": 2048},
            "model": {"type": ["string", "null"], "minLength": 1, "maxLength": 240},
            "context_window": {"type": "integer", "minimum": 512, "maximum": 2_000_000},
            "timeout_seconds": {"type": "number", "minimum": 1, "maximum": 600},
            "api_key": {"type": ["string", "null"], "maxLength": 512},
            "clear_api_key": {"type": "boolean"},
        },
        "required": ["name", "kind", "endpoint", "model", "context_window", "timeout_seconds"],
        "additionalProperties": False,
    }
    common: dict[str, Any] = {
        "source": "builtin",
        "provenance": "backend.app.services.llm_provider_profiles",
        "readiness": readiness,
        "availability": availability,
        "execution_owner": "backend.app.services.llm_provider_profiles.LLMProviderProfileStore",
        "timeout_policy": {"timeout_ms": PROVIDER_TIMEOUT_MS},
        "cancellation_policy": {"cancellable": False, "owner": "LLMProviderProfileStore"},
        "result_schema": {"type": "object"},
        "unavailable_explanation": explanation,
        "approval_mode": "same_turn",
    }
    destructive: dict[str, Any] = {
        **common,
        "cancellation_policy": {"cancellable": True, "owner": "LLMProviderProfileStore"},
        "boundaries": _boundaries(PROVIDER_TIMEOUT_MS, cancellable=True),
    }
    profile_ref = {
        "type": "object",
        "properties": {"profile_id": _PROFILE_ID},
        "required": ["profile_id"],
        "additionalProperties": False,
    }
    return (
        _capability(
            PROVIDER_PROFILE_WRITE,
            "local_write",
            **{**common, "input_schema": profile_write_schema},
        ),
        _capability(
            PROVIDER_PROFILE_DELETE,
            "destructive_action",
            **{**destructive, "input_schema": profile_ref},
        ),
        _capability(
            PROVIDER_SELECTION_UPDATE,
            "local_write",
            **{
                **common,
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "primary_profile_id": _PROFILE_ID,
                        "local_fallback_profile_id": {"type": "string", "maxLength": 128},
                        "cloud_escalation_enabled": {"type": "boolean"},
                        "cloud_profile_id": {"type": "string", "maxLength": 128},
                    },
                    "required": ["primary_profile_id", "cloud_escalation_enabled"],
                    "additionalProperties": False,
                },
            },
        ),
        _capability(
            PROVIDER_SECRET_ROTATE,
            "destructive_action",
            **{
                **destructive,
                "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
            },
        ),
        _capability(
            PROVIDER_CONNECTIVITY_TEST,
            "external_read",
            **{**common, "input_schema": profile_ref},
        ),
    )


def _operator(observation: CapabilityObservation) -> CapabilityDescriptor:
    present = observation.operator_config_present
    return _capability(
        OPERATOR_CONFIG_WRITE,
        "local_write",
        source="builtin",
        provenance="backend.app.services.operator_config_service",
        # The allowlist is surfaced for discovery, not enforced here: the service rejects
        # unknown keys per-field and reports them, which is richer than a schema refusal.
        input_schema={
            "type": "object",
            "properties": {"fields": {"type": "object"}},
            "required": ["fields"],
            "additionalProperties": False,
        },
        metadata_claims={
            "operator_fields": {"keys": list(observation.operator_config_keys), "trusted": False}
        },
        readiness="ready" if present else "unavailable",
        availability="available" if present else "misconfigured",
        execution_owner="backend.app.services.operator_config_service.OperatorConfigService",
        timeout_policy={"timeout_ms": CONFIG_TIMEOUT_MS},
        cancellation_policy={"cancellable": False, "owner": "OperatorConfigService"},
        result_schema={"type": "object"},
        unavailable_explanation="" if present else OPERATOR_CONFIG_UNAVAILABLE,
        approval_mode="same_turn",
    )


_DEFINITION_FAMILY = {"type": "string", "enum": ["mcp", "acp", "tool", "hook", "plugin"]}
_DEFINITION_ID = {"type": "string", "minLength": 1, "maxLength": 128}


def _extension_definitions(
    observation: CapabilityObservation,
) -> tuple[CapabilityDescriptor, ...]:
    """Operator-owned declarative definitions are created and removed as governed actions.

    This is what lets an operator manage an MCP connection without hand-editing YAML, while
    keeping one write path, one authorization ladder, and one evidence trail.
    """
    present = observation.extension_catalog_present
    common: dict[str, Any] = {
        "source": "builtin",
        "provenance": "backend.app.services.extension_runtime_service",
        "readiness": "ready" if present else "unavailable",
        "availability": "available" if present else "disabled",
        "execution_owner": (
            "backend.app.services.extension_runtime_service.ExtensionRuntimeService"
        ),
        "timeout_policy": {"timeout_ms": CONFIG_TIMEOUT_MS},
        "cancellation_policy": {"cancellable": False, "owner": "ExtensionRuntimeService"},
        "result_schema": {"type": "object"},
        "unavailable_explanation": "" if present else EXTENSION_CATALOG_UNAVAILABLE,
        "approval_mode": "same_turn",
    }
    return (
        _capability(
            EXTENSION_DEFINITION_WRITE,
            "local_write",
            input_schema={
                "type": "object",
                "properties": {
                    "family": _DEFINITION_FAMILY,
                    "local_id": _DEFINITION_ID,
                    "definition": {"type": "object"},
                    "name": {"type": "string", "minLength": 1, "maxLength": 200},
                    "version": {"type": "string", "minLength": 1, "maxLength": 64},
                    "enabled": {"type": "boolean"},
                },
                "required": ["family", "local_id", "definition", "name", "version"],
                "additionalProperties": False,
            },
            **common,
        ),
        _capability(
            EXTENSION_DEFINITION_DELETE,
            "local_write",
            input_schema={
                "type": "object",
                "properties": {"family": _DEFINITION_FAMILY, "local_id": _DEFINITION_ID},
                "required": ["family", "local_id"],
                "additionalProperties": False,
            },
            **common,
        ),
        _capability(
            EXTENSION_SKILL_WRITE,
            "local_write",
            input_schema={
                "type": "object",
                "properties": {
                    "local_id": _DEFINITION_ID,
                    "body": {"type": "string", "minLength": 1, "maxLength": 60000},
                },
                "required": ["local_id", "body"],
                "additionalProperties": False,
            },
            **common,
        ),
        _capability(
            EXTENSION_SKILL_DELETE,
            "local_write",
            input_schema={
                "type": "object",
                "properties": {"local_id": _DEFINITION_ID},
                "required": ["local_id"],
                "additionalProperties": False,
            },
            **common,
        ),
    )


def _extension(observation: CapabilityObservation) -> CapabilityDescriptor:
    present = observation.extension_catalog_present
    return _capability(
        EXTENSION_STATE_UPDATE,
        "local_write",
        source="builtin",
        provenance="backend.app.services.extension_service",
        input_schema={
            "type": "object",
            "properties": {
                "extension_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "state": {"type": "string", "enum": ["enabled", "disabled", "retired"]},
                "expected_revision": _REVISION,
                "reason": _REASON,
            },
            "required": ["extension_id", "state"],
            "additionalProperties": False,
        },
        readiness="ready" if present else "unavailable",
        availability="available" if present else "disabled",
        execution_owner="backend.app.services.extension_service.ExtensionService",
        timeout_policy={"timeout_ms": CONFIG_TIMEOUT_MS},
        cancellation_policy={"cancellable": False, "owner": "ExtensionService"},
        result_schema={"type": "object"},
        unavailable_explanation="" if present else EXTENSION_CATALOG_UNAVAILABLE,
        approval_mode="same_turn",
    )


def _agents(observation: CapabilityObservation) -> tuple[CapabilityDescriptor, ...]:
    descriptors = []
    for (
        capability_id,
        profile_id,
        _display_name,
        effect_class,
        auth_rule,
        timeout_ms,
        cancellable,
        unsupported,
    ) in observation.agents:
        descriptors.append(
            CapabilityDescriptor(
                capability_id=capability_id,
                source="config/agents",
                provenance="backend.app.agents.registry",
                input_schema={
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "minLength": 1, "maxLength": 4000},
                    },
                    "required": ["prompt"],
                    "additionalProperties": False,
                },
                effect_class=effect_class,
                readiness="ready" if not unsupported else "unavailable",
                availability="available" if not unsupported else "misconfigured",
                authorization_rule=auth_rule,
                execution_owner="backend.app.agents.invocation",
                timeout_policy={"timeout_ms": timeout_ms},
                cancellation_policy={"cancellable": cancellable},
                result_schema={
                    "type": "object",
                    "properties": {
                        "agent_id": {"type": "string"},
                        "output": {},
                        "status": {"type": "string"},
                    },
                },
                artifact_evidence={
                    "records": [
                        "action_proposals",
                        "authorization_decisions",
                        "delegated_runs",
                    ]
                },
                unavailable_explanation=unsupported,
                # An agent invocation is requested through the API, not proposed inside a
                # conversation turn, so its approval is decided on the operator surface.
                approval_mode="same_turn",
                metadata_claims={"agent_id": {"value": profile_id, "trusted": False}},
            )
        )
    return tuple(descriptors)


def _capability(
    capability_id: str,
    effect_class: EffectClass,
    *,
    boundaries: dict[str, Any] | None = None,
    **fields: Any,
) -> CapabilityDescriptor:
    authorization_rule = default_authorization(effect_class)
    records = ["action_proposals", "authorization_decisions", "action_execution_results"]
    if authorization_rule == "requires_approval":
        records.insert(2, "approval_records")
    if (boundaries or {}).get("cancellable"):
        records.append("action_cancellations")
    return CapabilityDescriptor(
        capability_id=capability_id,
        effect_class=effect_class,
        authorization_rule=authorization_rule,
        artifact_evidence={"records": records},
        boundaries=boundaries or {},
        **fields,
    )


def _boundaries(timeout_ms: int, *, cancellable: bool) -> dict[str, Any]:
    return {
        "storage_roots": [],
        "timeout_ms": timeout_ms,
        "cancellable": cancellable,
        "max_result_bytes": RESULT_BYTES,
    }
