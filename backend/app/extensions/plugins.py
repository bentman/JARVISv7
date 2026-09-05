from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from backend.app.actions.boundaries import ActionOperation
from backend.app.extensions.discovery import (
    DEFINITION_FAMILIES,
    SAFE_LOCAL_ID,
    DefinitionManifest,
    discover_definition_manifests,
    parse_definition_manifest,
)
from backend.app.extensions.lifecycle import PluginDefinition, validate_plugin_transition

_INSTALL_RECORD = "plugin-install.json"


@dataclass(frozen=True, slots=True)
class InstalledPluginChild:
    plugin_id: str
    family: str
    local_id: str
    path: Path


class PluginInstaller:
    def __init__(self, config_dir: Path, data_dir: Path) -> None:
        self._config_dir = config_dir
        self._data_dir = data_dir

    def install(self, manifest: DefinitionManifest, operation: ActionOperation) -> dict[str, Any]:
        source, children = self._validate_manifest(manifest)
        operation.check()
        bundle_hash = _bundle_hash(source, operation)
        destination_root = self._data_dir / "extensions" / "plugins"
        if destination_root.is_symlink() or any(parent.is_symlink() for parent in destination_root.parents):
            raise ValueError("plugin destination contains a symlink")
        destination = destination_root / manifest.local_id
        if destination.exists() or destination.is_symlink():
            return self._existing_result(destination, manifest, bundle_hash, children)

        destination_root.mkdir(parents=True, exist_ok=True)
        temporary = destination_root / f".{manifest.local_id}.install-{uuid.uuid4().hex}"
        try:
            _copy_bundle(source, temporary, operation)
            _write_record(temporary, manifest.local_id, bundle_hash, children)
            operation.check()
            os.replace(temporary, destination)
        except BaseException:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return _result(manifest.local_id, "installed", bundle_hash, children)

    def installed_definitions(self) -> tuple[InstalledPluginChild, ...]:
        root = self._data_dir / "extensions" / "plugins"
        if not root.is_dir() or root.is_symlink():
            return ()
        children: list[InstalledPluginChild] = []
        for directory in sorted(root.iterdir()):
            if not directory.is_dir() or directory.is_symlink() or directory.name.startswith("."):
                continue
            if not (directory / _INSTALL_RECORD).is_file():
                continue
            record = _read_record(directory)
            expected_hash = record["bundle_sha256"]
            if _bundle_hash(directory) != expected_hash:
                raise ValueError(f"installed plugin bundle changed: {directory.name}")
            for item in record["extensions"]:
                path = _contained_path(directory, item["path"])
                if not path.is_file():
                    raise ValueError(f"installed plugin child is unavailable: {item['path']}")
                children.append(
                    InstalledPluginChild(directory.name, item["family"], item["id"], path)
                )
        return tuple(sorted(children, key=lambda item: (item.family, item.local_id, item.plugin_id)))

    def _validate_manifest(
        self, manifest: DefinitionManifest
    ) -> tuple[Path, tuple[dict[str, str], ...]]:
        if manifest.family != "plugin":
            raise ValueError("plugin installer requires a plugin definition")
        source_value = manifest.definition.get("source")
        if not isinstance(source_value, str):
            raise ValueError("plugin definition source must be a relative directory")
        root = self._source_root(manifest)
        source = _contained_path(root, source_value)
        if not source.is_dir() or source.is_symlink():
            raise ValueError("plugin definition source must be a local directory")
        children = _validate_children(manifest.definition.get("extensions"), source)
        for item in children:
            child = parse_definition_manifest(item["family"], (source / item["path"]).read_text(encoding="utf-8"),
                                              item["path"], "data/extensions", "external")
            if child.local_id != item["id"]:
                raise ValueError("plugin child id does not match its definition")
            existing = discover_definition_manifests(item["family"], config_root=self._config_dir, data_root=self._data_dir)
            if any(record.local_id == child.local_id for record in existing.manifests):
                raise ValueError(f"plugin child collision: {item['family']}:{child.local_id}")
        PluginDefinition(
            plugin_id=manifest.local_id,
            version=manifest.version,
            state="installed",
            contained_extension_ids=tuple(f"{item['family']}:{item['id']}" for item in children),
            description=manifest.display_name,
        )
        validate_plugin_transition("discovered", "installed")
        return source, children

    def _source_root(self, manifest: DefinitionManifest) -> Path:
        if manifest.provenance == "config/extensions":
            return self._config_dir / "extensions" / "plugins"
        if manifest.provenance == "data/extensions":
            return self._data_dir / "extensions" / "plugins"
        raise ValueError("plugin definition provenance must be config/extensions or data/extensions")

    def _existing_result(
        self,
        destination: Path,
        manifest: DefinitionManifest,
        bundle_hash: str,
        children: tuple[dict[str, str], ...],
    ) -> dict[str, Any]:
        if not destination.is_dir() or destination.is_symlink():
            raise ValueError(f"plugin destination collision: {manifest.local_id}")
        record = _read_record(destination)
        if record["plugin_id"] != manifest.local_id or record["bundle_sha256"] != bundle_hash:
            raise ValueError(f"plugin destination collision: {manifest.local_id}")
        if tuple(record["extensions"]) != children or _bundle_hash(destination) != bundle_hash:
            raise ValueError(f"plugin destination collision: {manifest.local_id}")
        return _result(manifest.local_id, "already_installed", bundle_hash, children)


def _validate_children(value: Any, source: Path) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("plugin definition extensions must be a non-empty list")
    children: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for item in value:
        if not isinstance(item, dict) or set(item) != {"family", "id", "path"}:
            raise ValueError("plugin extensions entries must contain family, id, and path")
        family, local_id, path = item["family"], item["id"], item["path"]
        if family not in DEFINITION_FAMILIES:
            raise ValueError(f"plugin child family is unsupported: {family}")
        if not isinstance(local_id, str) or not SAFE_LOCAL_ID.match(local_id):
            raise ValueError(f"plugin child id must match {SAFE_LOCAL_ID.pattern}")
        if not isinstance(path, str):
            raise ValueError("plugin child path must be a relative file")
        resolved = _contained_path(source, path)
        if not resolved.is_file() or resolved.is_symlink():
            raise ValueError(f"plugin child path must be a local file: {path}")
        key = (family, local_id)
        if key in seen:
            raise ValueError(f"plugin child is duplicated: {family}:{local_id}")
        seen.add(key)
        children.append({"family": family, "id": local_id, "path": path})
    return tuple(children)


def _contained_path(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if (
        not relative
        or candidate.is_absolute()
        or candidate.drive
        or "\\" in relative
        or PurePosixPath(relative).is_absolute()
        or ".." in candidate.parts
    ):
        raise ValueError(f"plugin path must stay inside the bundle: {relative}")
    if root.is_symlink() or any(parent.is_symlink() for parent in root.parents):
        raise ValueError("plugin root contains a symlink")
    cursor = root
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"plugin path contains a symlink: {relative}")
    resolved_root = root.resolve()
    resolved = (root / candidate).resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"plugin path escapes the bundle: {relative}")
    return resolved


def _bundle_hash(root: Path, operation: ActionOperation | None = None) -> str:
    if root.is_symlink():
        raise ValueError("plugin bundle must not be a symlink")
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if operation is not None:
            operation.check()
        if path.name == _INSTALL_RECORD:
            continue
        if path.is_symlink():
            raise ValueError(f"plugin bundle contains a symlink: {path.name}")
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError(f"plugin bundle contains an unsupported path: {path.name}")
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as stream:
            while chunk := stream.read(64 * 1024):
                if operation is not None:
                    operation.check()
                digest.update(chunk)
    return digest.hexdigest()


def _copy_bundle(source: Path, destination: Path, operation: ActionOperation) -> None:
    destination.mkdir(parents=True)
    for path in sorted(source.rglob("*")):
        operation.check()
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_symlink():
            raise ValueError(f"plugin bundle contains a symlink: {relative.as_posix()}")
        if path.is_dir():
            target.mkdir(exist_ok=True)
        elif path.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        else:
            raise ValueError(f"plugin bundle contains an unsupported path: {relative.as_posix()}")


def _write_record(
    destination: Path, plugin_id: str, bundle_hash: str, children: tuple[dict[str, str], ...]
) -> None:
    payload = {"plugin_id": plugin_id, "bundle_sha256": bundle_hash, "extensions": list(children)}
    (destination / _INSTALL_RECORD).write_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )


def _read_record(destination: Path) -> dict[str, Any]:
    record = destination / _INSTALL_RECORD
    if record.is_symlink():
        raise ValueError(f"plugin destination collision: {destination.name}")
    try:
        payload = json.loads(record.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"plugin destination collision: {destination.name}") from exc
    if not isinstance(payload, dict) or set(payload) != {"plugin_id", "bundle_sha256", "extensions"}:
        raise ValueError(f"plugin destination collision: {destination.name}")
    if not isinstance(payload["plugin_id"], str) or not SAFE_LOCAL_ID.match(payload["plugin_id"]):
        raise ValueError(f"plugin destination collision: {destination.name}")
    if not isinstance(payload["bundle_sha256"], str) or len(payload["bundle_sha256"]) != 64:
        raise ValueError(f"plugin destination collision: {destination.name}")
    children = _validate_children(payload["extensions"], destination)
    return {"plugin_id": payload["plugin_id"], "bundle_sha256": payload["bundle_sha256"], "extensions": children}


def _result(
    plugin_id: str, status: str, bundle_hash: str, children: tuple[dict[str, str], ...]
) -> dict[str, Any]:
    return {
        "plugin_id": plugin_id,
        "status": status,
        "bundle_sha256": bundle_hash,
        "extensions": [dict(item) for item in children],
    }


__all__ = ["InstalledPluginChild", "PluginInstaller"]
