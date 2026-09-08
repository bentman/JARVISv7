from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from backend.app.core.paths import CONFIG_DIR, DATA_DIR

DefinitionFamily = Literal["mcp", "acp", "hook", "plugin", "tool"]
DEFINITION_FAMILIES = frozenset({"mcp", "acp", "hook", "plugin", "tool"})
DEFINITION_DIRECTORIES = {
    "mcp": "mcp",
    "acp": "acp",
    "hook": "hooks",
    "plugin": "plugins",
    "tool": "tools",
}
SAFE_LOCAL_ID = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_SECRET_KEY = re.compile(r"(?:api[_-]?key|credential|password|secret|token|authorization)", re.I)
_ALLOWED_FIELDS = {
    "id", "name", "version", "definition", "enabled", "dependencies", "metadata",
}
UNOBSERVED_EXPLANATION = "No runtime observer is registered for this extension."


@dataclass(frozen=True, slots=True)
class DefinitionManifest:
    family: DefinitionFamily
    local_id: str
    display_name: str
    version: str
    source: str
    provenance: str
    trust: str
    declared_enabled: bool = True
    readiness: str = "unavailable"
    availability: str = "unknown"
    unavailable_explanation: str = UNOBSERVED_EXPLANATION
    dependencies: tuple[str, ...] = ()
    metadata_claims: dict[str, Any] = field(default_factory=dict)
    definition: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DefinitionError:
    family: str
    source: str
    reason: str


@dataclass(frozen=True, slots=True)
class DefinitionRuntime:
    family: DefinitionFamily
    local_id: str
    readiness: str
    availability: str
    unavailable_explanation: str = ""

    def __post_init__(self) -> None:
        _require_family(self.family)
        if not SAFE_LOCAL_ID.match(self.local_id):
            raise ValueError(f"local_id must match {SAFE_LOCAL_ID.pattern}")
        if self.readiness not in {"ready", "degraded", "unavailable"}:
            raise ValueError("readiness must be ready, degraded, or unavailable")
        if self.availability not in {"available", "disabled", "misconfigured", "unknown"}:
            raise ValueError("availability must be available, disabled, misconfigured, or unknown")
        if self.availability != "available" and not self.unavailable_explanation:
            raise ValueError("unavailable_explanation is required when availability is not available")


@dataclass(frozen=True, slots=True)
class DefinitionList:
    manifests: list[DefinitionManifest] = field(default_factory=list)
    errors: list[DefinitionError] = field(default_factory=list)


def definitions_directory(
    family: DefinitionFamily, *, config_root: Path | None = None, data_root: Path | None = None
) -> tuple[Path, Path]:
    _require_family(family)
    return (
        (config_root or CONFIG_DIR) / "extensions" / DEFINITION_DIRECTORIES[family],
        (data_root or DATA_DIR) / "extensions" / DEFINITION_DIRECTORIES[family],
    )


def discover_definition_manifests(
    family: DefinitionFamily,
    *,
    config_root: Path | None = None,
    data_root: Path | None = None,
) -> DefinitionList:
    """Discover declarative definitions without executing or resolving any extension content."""
    config_dir, data_dir = definitions_directory(
        family, config_root=config_root, data_root=data_root
    )
    result = DefinitionList()
    accepted: dict[str, DefinitionManifest] = {}
    for root, provenance, trust in (
        (config_dir, "config/extensions", "application"),
        (data_dir, "data/extensions", "operator"),
    ):
        for path in _definition_paths(root):
            source = _relative_source(path)
            try:
                manifest = parse_definition_manifest(
                    family, path.read_text(encoding="utf-8"), source, provenance, trust
                )
            except (OSError, ValueError, yaml.YAMLError) as exc:
                result.errors.append(DefinitionError(family, source, str(exc)))
                continue
            existing = accepted.get(manifest.local_id)
            if existing is not None:
                result.errors.append(
                    DefinitionError(
                        family,
                        source,
                        f"duplicate {family} id '{manifest.local_id}'; retained {existing.source}",
                    )
                )
                continue
            accepted[manifest.local_id] = manifest
    return DefinitionList(
        manifests=[accepted[key] for key in sorted(accepted)], errors=result.errors
    )


def parse_definition_manifest(
    family: DefinitionFamily,
    text: str,
    source: str,
    provenance: str,
    trust: str,
) -> DefinitionManifest:
    _require_family(family)
    payload = yaml.safe_load(text)
    if not isinstance(payload, dict):
        raise ValueError("definition must be a YAML mapping")
    unknown = sorted(set(payload) - _ALLOWED_FIELDS)
    if unknown:
        raise ValueError(f"definition contains unknown fields: {', '.join(unknown)}")
    missing = sorted({"id", "name", "version", "definition"} - set(payload))
    if missing:
        raise ValueError(f"definition is missing fields: {', '.join(missing)}")
    _reject_secret_keys(payload)
    local_id = payload["id"]
    if not isinstance(local_id, str) or not SAFE_LOCAL_ID.match(local_id):
        raise ValueError(f"id must match {SAFE_LOCAL_ID.pattern}")
    for field_name in ("name", "version"):
        if not isinstance(payload[field_name], str) or not payload[field_name].strip():
            raise ValueError(f"{field_name} must be a non-empty string")
    definition = payload["definition"]
    if not isinstance(definition, dict):
        raise ValueError("definition must be a mapping")
    enabled = payload.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    dependencies = payload.get("dependencies", [])
    if not isinstance(dependencies, list) or any(not isinstance(item, str) or not item for item in dependencies):
        raise ValueError("dependencies must be a list of non-empty strings")
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be a mapping")
    return DefinitionManifest(
        family=family,
        local_id=local_id,
        display_name=payload["name"],
        version=payload["version"],
        source=source,
        provenance=provenance,
        trust=trust,
        declared_enabled=enabled,
        dependencies=tuple(dependencies),
        metadata_claims={"declaration": {"values": metadata, "trusted": False}},
        definition=definition,
    )


def _definition_paths(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        return []
    return [
        path for path in sorted(root.glob("*"))
        if path.is_file() and not path.is_symlink() and path.suffix.lower() in {".yaml", ".yml"}
    ]


def _relative_source(path: Path) -> str:
    try:
        return str(path.relative_to(CONFIG_DIR.parent)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _reject_secret_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise ValueError("definition keys must be strings")
            # A "_url" names a public endpoint and a "_ref" names a stored secret by
            # reference; neither carries the secret itself. Without this, an OAuth block
            # could never declare authorization_url or token_url.
            if _SECRET_KEY.search(key) and not key.endswith(("_ref", "_url")):
                raise ValueError(f"secret-bearing field is not allowed: {key}")
            _reject_secret_keys(child)
    elif isinstance(value, list):
        for child in value:
            _reject_secret_keys(child)


def _require_family(family: str) -> None:
    if family not in DEFINITION_FAMILIES:
        raise ValueError(f"definition family must be one of: {', '.join(sorted(DEFINITION_FAMILIES))}")


__all__ = [
    "DEFINITION_DIRECTORIES", "DEFINITION_FAMILIES", "DefinitionError", "DefinitionFamily",
    "DefinitionList", "DefinitionManifest", "DefinitionRuntime", "definitions_directory",
    "discover_definition_manifests", "parse_definition_manifest",
]
