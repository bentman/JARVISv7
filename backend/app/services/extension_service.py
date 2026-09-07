from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.extensions.catalog import (
    ExtensionObservation,
    build_extension_descriptors,
)
from backend.app.extensions.contracts import ExtensionCatalog, ExtensionError
from backend.app.extensions.discovery import DEFINITION_FAMILIES, discover_definition_manifests
from backend.app.extensions.prompts import list_prompt_templates_with_errors, load_prompt_template
from backend.app.extensions.skills import list_skills_with_errors, load_skill_body
from backend.app.extensions.store import ExtensionOverlayConflictError, ExtensionOverlayStore

MAX_EVENTS = 20


@dataclass(frozen=True, slots=True)
class ExtensionServiceError(Exception):
    status_code: int
    error: str
    message: str
    current_revision: int | None = None

    def detail(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"error": self.error, "message": self.message}
        if self.current_revision is not None:
            payload["current_revision"] = self.current_revision
        return payload


@dataclass(frozen=True, slots=True)
class ExtensionView:
    extension_id: str
    family: str
    local_id: str
    version: str
    display_name: str
    source: str
    provenance: str
    trust: str
    state: str
    readiness: str
    availability: str
    unavailable_explanation: str
    dependencies: list[str]
    collisions: list[str]
    metadata_claims: dict[str, Any]
    revision: int | None = None
    body_available: bool = False


@dataclass(frozen=True, slots=True)
class ExtensionCatalogView:
    extensions: list[ExtensionView] = field(default_factory=list)
    families: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtensionLoadErrorView:
    family: str
    source: str
    reason: str


@dataclass(frozen=True, slots=True)
class ExtensionErrorListView:
    errors: list[ExtensionLoadErrorView] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ExtensionBodyView:
    extension_id: str
    body: str


class ExtensionService:
    def __init__(
        self,
        *,
        observe: Callable[[], ExtensionObservation],
        store: ExtensionOverlayStore | None = None,
        config_dir: Path | None = None,
        data_dir: Path | None = None,
    ) -> None:
        self._observe = observe
        self._store = store or ExtensionOverlayStore()
        self._config_dir = config_dir
        self._data_dir = data_dir
        self._lock = threading.RLock()
        self._catalog = ExtensionCatalog()
        self._errors: list[ExtensionLoadErrorView] = []
        self.refresh()

    def refresh(self) -> None:
        observation = self._observe()
        overlay = self._store.all_overlays()
        catalog = ExtensionCatalog()
        for descriptor in build_extension_descriptors(observation, overlay):
            catalog.register(descriptor)
        errors = [
            ExtensionLoadErrorView("personality", source, reason)
            for source, reason in observation.personality_errors
        ]
        errors += [
            ExtensionLoadErrorView("prompt", error.prompt_path, error.reason)
            for error in observation.prompt_errors
        ]
        errors += [
            ExtensionLoadErrorView("skill", error.skill_path, error.reason)
            for error in observation.skill_errors
        ]
        errors += [
            ExtensionLoadErrorView(error.family, error.source, error.reason)
            for error in observation.definition_errors
        ]
        with self._lock:
            self._catalog = catalog
            self._errors = errors

    def catalog(self) -> ExtensionCatalogView:
        self.refresh()
        with self._lock:
            rows = self._catalog.snapshot()
            families = self._catalog.families()
        return ExtensionCatalogView(
            extensions=[self._view(row) for row in rows], families=families
        )

    def read(self, extension_id: str) -> ExtensionView:
        self.refresh()
        with self._lock:
            descriptor = self._catalog.get(extension_id)
        if descriptor is None:
            raise ExtensionServiceError(404, "unknown_extension", "no extension matches that id")
        return self._view(descriptor.to_dict())

    def errors(self) -> ExtensionErrorListView:
        self.refresh()
        with self._lock:
            return ExtensionErrorListView(errors=list(self._errors))

    def set_state(
        self, *, extension_id: str, state: str, expected_revision: int | None, reason: str | None
    ) -> ExtensionView:
        self.read(extension_id)
        try:
            self._store.set_state(
                extension_id=extension_id,
                state=state,
                expected_revision=expected_revision,
                reason=reason,
            )
        except ExtensionOverlayConflictError as exc:
            raise ExtensionServiceError(
                409, "conflict", str(exc), exc.current_revision
            ) from exc
        except ExtensionError as exc:
            raise ExtensionServiceError(422, "invalid", str(exc)) from exc
        return self.read(extension_id)

    def body(self, extension_id: str) -> ExtensionBodyView:
        descriptor_view = self.read(extension_id)
        if not descriptor_view.body_available:
            raise ExtensionServiceError(
                404, "no_body", "this extension family does not expose a body"
            )
        try:
            if descriptor_view.family == "prompt":
                body = load_prompt_template(descriptor_view.local_id, self._config_dir).body
            else:
                body = load_skill_body(descriptor_view.local_id, self._data_dir)
        except FileNotFoundError as exc:
            raise ExtensionServiceError(404, "not_found", "extension body is unavailable") from exc
        except ValueError as exc:
            raise ExtensionServiceError(422, "invalid", str(exc)) from exc
        return ExtensionBodyView(extension_id=extension_id, body=body)

    def _view(self, row: dict[str, Any]) -> ExtensionView:
        overlay = self._store.read(row["extension_id"])
        return ExtensionView(
            extension_id=row["extension_id"],
            family=row["family"],
            local_id=row["local_id"],
            version=row["version"],
            display_name=row["display_name"],
            source=row["source"],
            provenance=row["provenance"],
            trust=row["trust"],
            state=row["state"],
            readiness=row["readiness"],
            availability=row["availability"],
            unavailable_explanation=row["unavailable_explanation"],
            dependencies=list(row["dependencies"]),
            collisions=list(row["collisions"]),
            metadata_claims=row["metadata_claims"],
            revision=overlay.revision if overlay else None,
            body_available=row["family"] in {"prompt", "skill"},
        )


def observe_extensions(
    *,
    settings_provider: Callable[[], Any],
    personality_provider: Callable[[], Any],
    provider_store_factory: Callable[[], Any] | None = None,
    capability_service_provider: Callable[[], Any] | None = None,
    operator_config_keys: tuple[str, ...] = (),
    config_dir: Path | None = None,
    data_dir: Path | None = None,
    runtime_provider: Callable[[], Any] | None = None,
    agent_registry_provider: Callable[[], Any] | None = None,
) -> ExtensionObservation:
    from backend.app.core.settings import SETTING_ENV_CLASSIFICATION
    from backend.app.services.llm_provider_profiles import SecretStoreLockedError

    settings = settings_provider()
    personality = personality_provider()
    personalities = tuple(
        (
            profile.profile_id,
            profile.display_name,
            bool(getattr(profile, "enabled", True)),
            f"config/personality/{profile.profile_id}.yaml",
        )
        for profile in getattr(personality, "profiles", [])
    )
    personality_errors = tuple(
        (error.profile_path, error.reason) for error in getattr(personality, "errors", [])
    )

    providers: tuple[tuple[str, str, str, bool], ...] = ()
    store_locked = False
    if provider_store_factory is not None:
        try:
            profiles = provider_store_factory().list_profiles(settings)
            providers = tuple(
                (profile.profile_id, profile.name, profile.readiness_state, profile.builtin)
                for profile in profiles
            )
        except SecretStoreLockedError:
            store_locked = True
        except Exception:
            providers = ()

    capabilities: tuple[tuple[str, str, str], ...] = ()
    if capability_service_provider is not None:
        service = capability_service_provider()
        if service is not None:
            capabilities = tuple(
                (item.capability_id, item.readiness, item.availability)
                for item in service.catalog().capabilities
            )

    prompt_list = list_prompt_templates_with_errors(config_dir)
    skill_list = (
        list_skills_with_errors(data_dir)
        if config_dir is not None and data_dir is not None and config_dir == data_dir
        else list_skills_with_errors(data_dir, config_dir=config_dir)
    )
    definition_lists = tuple(
        discover_definition_manifests(family, config_root=config_dir, data_root=data_dir)
        for family in sorted(DEFINITION_FAMILIES)
    )
    runtime = runtime_provider() if runtime_provider else None
    runtime_definitions, runtime_records, runtime_errors = runtime.observation() if runtime else ((), (), ())

    agent_records: tuple[tuple[str, str, str, str], ...] = ()
    if agent_registry_provider is not None:
        registry = agent_registry_provider()
        if registry is not None:
            agent_records = tuple(registry.to_extension_records())

    return ExtensionObservation(
        settings=tuple(
            (key, SETTING_ENV_CLASSIFICATION.get(key, "advanced")) for key in operator_config_keys
        ),
        personalities=personalities,
        personality_errors=personality_errors,
        providers=providers,
        provider_store_locked=store_locked,
        search_providers=(
            ("ddgs", bool(getattr(settings, "use_ddgs", False))),
            ("searxng", bool(getattr(settings, "use_searxng", False))),
            ("tavily", bool(getattr(settings, "use_tavily", False))),
        ),
        prompts=tuple(prompt_list.templates),
        prompt_errors=tuple(prompt_list.errors),
        skills=tuple(skill_list.skills),
        skill_errors=tuple(skill_list.errors),
        executable_skills=tuple(runtime.executable_skills()) if runtime else (),
        capabilities=capabilities,
        definitions=runtime_definitions if runtime is not None else tuple(
            manifest for definition_list in definition_lists for manifest in definition_list.manifests
        ),
        definition_runtime=runtime_records,
        definition_errors=runtime_errors + tuple(
            error for definition_list in definition_lists for error in definition_list.errors
        ),
        agents=agent_records,
    )


__all__ = [
    "ExtensionBodyView",
    "ExtensionCatalogView",
    "ExtensionErrorListView",
    "ExtensionLoadErrorView",
    "ExtensionService",
    "ExtensionServiceError",
    "ExtensionView",
    "observe_extensions",
]
