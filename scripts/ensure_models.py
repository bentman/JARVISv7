from __future__ import annotations

import argparse
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import httpx
from huggingface_hub import hf_hub_download

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.capabilities import HardwareProfile
from backend.app.core.logging import configure_logging, emit_host_fingerprint
from backend.app.core.settings import load_settings
from backend.app.models.catalog import ModelEntry, get_model_entry, list_models
from backend.app.models.llm_selection import select_llm_model
from backend.app.hardware.provisioning import resolve_required_extras

MODEL_FAMILIES = ("stt", "tts", "wake")
ALL_FAMILIES = (*MODEL_FAMILIES, "llm")
_PENDING_RUNTIME_SOURCE_TYPES = {"pending-pinned-release", "pending-viability", "build-required"}


def _load_profiler():
    from backend.app.hardware.profiler import run_profiler

    return run_profiler


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ensure_models.py")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--trace-to")
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--family", choices=ALL_FAMILIES)
    parser.add_argument("--model")
    parser.add_argument("--llm-policy")
    parser.add_argument("--all-llm", action="store_true")
    return parser.parse_args(argv)


def _explicit_cli(args: argparse.Namespace) -> bool:
    return bool(
        getattr(args, "family", None)
        or getattr(args, "model", None)
        or getattr(args, "llm_policy", None)
        or getattr(args, "all_llm", False)
    )


def _source_files(entry: ModelEntry) -> list[tuple[str, str]]:
    source = entry.source
    file_name = source.get("file")
    if isinstance(file_name, str) and file_name.strip():
        target_name = entry.local_path.name if _entry_targets_single_file(entry) else Path(file_name).name
        return [(target_name, file_name)]
    files = source.get("files", [])
    if isinstance(files, list):
        return [(str(file_name), str(file_name)) for file_name in files]
    if isinstance(files, dict):
        return [(str(file_name), str(source_ref)) for file_name, source_ref in files.items()]
    raise ValueError(f"model '{entry.name}' has invalid source files metadata")


def _entry_targets_single_file(entry: ModelEntry) -> bool:
    source = entry.source
    file_name = source.get("file")
    files = source.get("files")
    return isinstance(file_name, str) and file_name.strip() and files is None and bool(entry.local_path.suffix)


def _target_for_file(entry: ModelEntry, file_name: str) -> Path:
    if _entry_targets_single_file(entry):
        return entry.local_path
    return entry.local_path / file_name


def _relative_local_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _missing_artifact_reason(entry: ModelEntry, missing: list[str]) -> str | None:
    if entry.family == "llm" and missing:
        return "Degraded-no-local-model-artifact"
    return None


def _hardware_profiles(entry: ModelEntry) -> dict[str, dict[str, Any]]:
    serve_profiles = entry.config.get("serve_profiles", {})
    if not isinstance(serve_profiles, dict):
        raise ValueError(f"model '{entry.name}' has invalid serve_profiles metadata")
    profiles = serve_profiles.get("hardware_profiles", serve_profiles)
    if not isinstance(profiles, dict):
        raise ValueError(f"model '{entry.name}' has invalid serve_profiles.hardware_profiles metadata")
    return {
        profile_id: profile
        for profile_id, profile in profiles.items()
        if isinstance(profile_id, str) and isinstance(profile, dict)
    }


def _runtime_binary_path(profile_id: str, profile: dict[str, Any]) -> Path:
    artifact = profile.get("runtime_artifact", {})
    raw_path: object = None
    if isinstance(artifact, dict):
        raw_path = artifact.get("binary_path")
    if raw_path is None:
        raw_path = profile.get("binary_path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError(f"LLM serve profile '{profile_id}' has no runtime binary path")
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def _runtime_source(profile: dict[str, Any]) -> dict[str, Any]:
    artifact = profile.get("runtime_artifact", {})
    if not isinstance(artifact, dict):
        raise ValueError("runtime_artifact metadata must be a mapping")
    source = artifact.get("source", {})
    if not isinstance(source, dict):
        raise ValueError("runtime_artifact.source metadata must be a mapping")
    return source


def _runtime_source_type(profile: dict[str, Any]) -> str:
    source_type = _runtime_source(profile).get("type")
    if not isinstance(source_type, str) or not source_type.strip():
        raise ValueError("runtime_artifact.source.type must be a non-empty string")
    return source_type


def _runtime_required_files(profile_id: str, profile: dict[str, Any]) -> list[str]:
    artifact = profile.get("runtime_artifact", {})
    required = artifact.get("required_files", []) if isinstance(artifact, dict) else []
    if required is None:
        required = []
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        raise ValueError(f"LLM serve profile '{profile_id}' has invalid runtime required_files")
    if required:
        return required
    return [_runtime_binary_path(profile_id, profile).name]


def _runtime_required_extensions(profile_id: str, profile: dict[str, Any]) -> list[str]:
    artifact = profile.get("runtime_artifact", {})
    adjacent = artifact.get("required_adjacent", {}) if isinstance(artifact, dict) else {}
    extensions = adjacent.get("dll_extensions", []) if isinstance(adjacent, dict) else []
    if extensions is None:
        extensions = []
    if not isinstance(extensions, list) or not all(isinstance(item, str) for item in extensions):
        raise ValueError(f"LLM serve profile '{profile_id}' has invalid runtime dll_extensions")
    return extensions


def _runtime_missing_reason(profile: dict[str, Any], source: dict[str, Any], missing: list[str]) -> str | None:
    if not missing:
        return None
    source_type = source.get("type")
    if source_type == "build-required":
        return "SKIP-build-required"
    if source_type == "pending-viability":
        return "SKIP-no-viable-binary"
    if source_type == "pending-pinned-release":
        return "SKIP-source-pending"
    close_reason = profile.get("close_if_unavailable")
    if isinstance(close_reason, str) and close_reason.strip():
        return close_reason
    return "Degraded-no-sidecar-binary"


def _verify_runtime_profile(profile_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    binary_path = _runtime_binary_path(profile_id, profile)
    source = _runtime_source(profile)
    required_files = _runtime_required_files(profile_id, profile)
    required_extensions = _runtime_required_extensions(profile_id, profile)
    root = binary_path.parent
    discovered_files = [path for path in root.rglob("*") if path.is_file() and path.stat().st_size > 0]
    discovered_names = {path.name for path in discovered_files}
    discovered_exts = {path.suffix.lower() for path in discovered_files}

    missing: list[str] = []
    if not binary_path.is_file() or binary_path.stat().st_size <= 0:
        missing.append(binary_path.name)
    for file_name in required_files:
        if file_name not in discovered_names and file_name not in missing:
            missing.append(file_name)
    for extension in required_extensions:
        normalized = extension.lower()
        if normalized not in discovered_exts:
            missing.append(f"*{normalized}")

    present = sorted(str(path.relative_to(root)).replace("\\", "/") for path in discovered_files)
    reason = _runtime_missing_reason(profile, source, missing)
    ready = not missing
    state = "ready" if ready else ("skipped" if reason and reason.startswith("SKIP-") else "degraded")
    return {
        "profile_id": profile_id,
        "accelerator": str(profile.get("accelerator", "cpu")),
        "binary_path": _relative_local_path(binary_path),
        "source_type": str(source.get("type", "unknown")),
        "present": present,
        "missing": missing,
        "ready": ready,
        "state": state,
        "degraded_reason": reason,
    }


def _runtime_profile_matches_host(
    profile_id: str,
    profile: dict[str, Any],
    hardware_profile: HardwareProfile | None,
    extras: list[str] | None,
) -> bool:
    del profile_id
    if hardware_profile is None:
        return False
    if profile.get("os") != hardware_profile.os_name or profile.get("arch") != hardware_profile.arch:
        return False
    accelerator = str(profile.get("accelerator", "cpu"))
    if accelerator == "cpu":
        return True
    provisioning_extras = profile.get("provisioning_extras", [])
    if not isinstance(provisioning_extras, list) or extras is None:
        return False
    return any(isinstance(extra, str) and extra in extras for extra in provisioning_extras)


def _runtime_current_host_summary(
    profiles: dict[str, dict[str, Any]],
    results: list[dict[str, Any]],
    hardware_profile: HardwareProfile | None,
    extras: list[str] | None,
) -> dict[str, Any] | None:
    if hardware_profile is None:
        return None
    by_id = {str(result["profile_id"]): result for result in results}
    applicable_ids = [
        profile_id
        for profile_id, profile in profiles.items()
        if _runtime_profile_matches_host(profile_id, profile, hardware_profile, extras)
    ]
    if not applicable_ids:
        return {
            "os": hardware_profile.os_name,
            "arch": hardware_profile.arch,
            "applicable_profiles": [],
            "selected_profile_id": None,
            "selected_state": "missing",
            "selected_degraded_reason": "No current-host runtime artifact profile",
        }
    ready_accelerator = next(
        (
            profile_id
            for profile_id in applicable_ids
            if by_id.get(profile_id, {}).get("ready") and by_id[profile_id].get("accelerator") != "cpu"
        ),
        None,
    )
    cpu_profile_id = f"{hardware_profile.os_name}_{hardware_profile.arch}_cpu"
    selected_profile_id = ready_accelerator or (cpu_profile_id if cpu_profile_id in applicable_ids else applicable_ids[0])
    selected = by_id.get(selected_profile_id, {})
    return {
        "os": hardware_profile.os_name,
        "arch": hardware_profile.arch,
        "applicable_profiles": applicable_ids,
        "selected_profile_id": selected_profile_id,
        "selected_state": selected.get("state"),
        "selected_ready": selected.get("ready", False),
        "selected_degraded_reason": selected.get("degraded_reason"),
    }


def _current_host_runtime_profiles(
    profiles: dict[str, dict[str, Any]],
    hardware_profile: HardwareProfile | None,
    extras: list[str] | None,
) -> dict[str, dict[str, Any]]:
    if hardware_profile is None:
        return profiles
    return {
        profile_id: profile
        for profile_id, profile in profiles.items()
        if _runtime_profile_matches_host(profile_id, profile, hardware_profile, extras)
    }


def _verify_runtime_artifacts(
    entry: ModelEntry,
    hardware_profile: HardwareProfile | None = None,
    extras: list[str] | None = None,
    current_host_only: bool = False,
) -> dict[str, Any]:
    all_profiles = _hardware_profiles(entry)
    profiles = _current_host_runtime_profiles(all_profiles, hardware_profile, extras) if current_host_only else all_profiles
    results = [_verify_runtime_profile(profile_id, profile) for profile_id, profile in profiles.items()]
    payload = {
        "model": entry.name,
        "profiles": results,
        "ready": all(result["ready"] for result in results),
    }
    current_host = _runtime_current_host_summary(profiles, results, hardware_profile, extras)
    if current_host is not None:
        payload["current_host"] = current_host
    return payload


def _planned_runtime_profile(profile_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    binary_path = _runtime_binary_path(profile_id, profile)
    source = _runtime_source(profile)
    source_type = _runtime_source_type(profile)
    if source_type in _PENDING_RUNTIME_SOURCE_TYPES:
        if source_type == "pending-viability":
            reason = "SKIP-no-viable-binary"
        elif source_type == "build-required":
            reason = "SKIP-build-required"
        else:
            reason = "SKIP-source-pending"
        return {
            "profile_id": profile_id,
            "accelerator": str(profile.get("accelerator", "cpu")),
            "binary_path": _relative_local_path(binary_path),
            "source_type": source_type,
            "planned": [],
            "ready": False,
            "state": "skipped",
            "degraded_reason": reason,
        }
    return {
        "profile_id": profile_id,
        "accelerator": str(profile.get("accelerator", "cpu")),
        "binary_path": _relative_local_path(binary_path),
        "source_type": str(source.get("type", "unknown")),
        "planned": _runtime_required_files(profile_id, profile),
        "ready": True,
        "state": "planned",
        "degraded_reason": None,
    }


def _download_runtime_url_zip(profile_id: str, profile: dict[str, Any], dry_run: bool) -> list[str]:
    source = _runtime_source(profile)
    source_type = _runtime_source_type(profile)
    if source_type not in {"url_zip", "url_zip_set"}:
        raise ValueError(f"LLM serve profile '{profile_id}' has unsupported runtime source type '{source_type}'")
    archives = _runtime_source_archives(profile_id, source)
    if dry_run:
        return _runtime_required_files(profile_id, profile)

    binary_path = _runtime_binary_path(profile_id, profile)
    binary_path.parent.mkdir(parents=True, exist_ok=True)

    extracted: list[str] = []
    with httpx.Client(follow_redirects=True, timeout=300.0) as client:
        for runtime_archive in archives:
            response = client.get(runtime_archive["url"])
            response.raise_for_status()
            extracted.extend(_extract_runtime_zip_payload(response.content, binary_path.parent))
    if not extracted:
        raise RuntimeError(f"runtime artifact source for profile '{profile_id}' extracted no files")
    return extracted


def _runtime_source_archives(profile_id: str, source: dict[str, Any]) -> list[dict[str, str]]:
    source_type = source.get("type")
    if source_type == "url_zip":
        url = source.get("url")
        if not isinstance(url, str) or not url.startswith("https://"):
            raise ValueError(f"LLM serve profile '{profile_id}' has invalid runtime url_zip source")
        return [{"url": url}]
    if source_type == "url_zip_set":
        archives = source.get("archives")
        if not isinstance(archives, list) or not archives:
            raise ValueError(f"LLM serve profile '{profile_id}' has invalid runtime url_zip_set source")
        parsed: list[dict[str, str]] = []
        for archive in archives:
            if not isinstance(archive, dict):
                raise ValueError(f"LLM serve profile '{profile_id}' has invalid runtime url_zip_set source")
            url = archive.get("url")
            if not isinstance(url, str) or not url.startswith("https://"):
                raise ValueError(f"LLM serve profile '{profile_id}' has invalid runtime url_zip_set source")
            parsed.append({"url": url})
        return parsed
    raise ValueError(f"LLM serve profile '{profile_id}' has unsupported runtime source type '{source_type}'")


def _extract_runtime_zip_payload(payload: bytes, target_root: Path) -> list[str]:
    extracted: list[str] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        strip_prefix = _zip_common_file_prefix(archive.infolist())
        for member in archive.infolist():
            if member.is_dir():
                continue
            target_name = _zip_member_target(member.filename, strip_prefix)
            if target_name is None:
                continue
            target = target_root / target_name
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, target.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            extracted.append(str(target_name).replace("\\", "/"))
    return extracted


def _ensure_runtime_profile(profile_id: str, profile: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    source = _runtime_source(profile)
    source_type = _runtime_source_type(profile)
    if dry_run:
        return _planned_runtime_profile(profile_id, profile)
    existing = _verify_runtime_profile(profile_id, profile)
    if existing["ready"]:
        return {**existing, "acquired": []}
    if source_type in {"url_zip", "url_zip_set"}:
        acquired = _download_runtime_url_zip(profile_id, profile, dry_run=False)
        verify = _verify_runtime_profile(profile_id, profile)
        return {**verify, "acquired": acquired}
    return {
        **existing,
        "acquired": [],
        "state": "skipped",
        "degraded_reason": existing["degraded_reason"] or f"SKIP-unsupported-runtime-source:{source_type}",
    }


def _ensure_runtime_artifacts(
    entry: ModelEntry,
    dry_run: bool,
    hardware_profile: HardwareProfile | None = None,
    extras: list[str] | None = None,
    current_host_only: bool = False,
) -> dict[str, Any]:
    all_profiles = _hardware_profiles(entry)
    profiles = _current_host_runtime_profiles(all_profiles, hardware_profile, extras) if current_host_only else all_profiles
    results = [
        _ensure_runtime_profile(profile_id, profile, dry_run=dry_run)
        for profile_id, profile in profiles.items()
    ]
    payload = {
        "model": entry.name,
        "profiles": results,
        "ready": all(result["ready"] for result in results),
    }
    current_host = _runtime_current_host_summary(profiles, results, hardware_profile, extras)
    if current_host is not None:
        payload["current_host"] = current_host
    return payload


def _runtime_fetch_allowed(args: argparse.Namespace) -> tuple[bool, str]:
    if _explicit_cli(args):
        return True, "explicit-cli"
    settings = load_settings()
    if not settings.use_local_model:
        return False, "local model disabled"
    if not settings.local_model_fetch:
        return False, "LOCAL_MODEL_FETCH disabled"
    return True, "automatic-local-fetch-enabled"


def _zip_common_file_prefix(members: list[zipfile.ZipInfo]) -> str | None:
    file_parts = [
        _zip_member_parts(member.filename)
        for member in members
        if not member.is_dir()
    ]
    if not file_parts or not all(len(parts) > 1 for parts in file_parts):
        return None
    prefix = file_parts[0][0]
    if all(parts[0] == prefix for parts in file_parts):
        return prefix
    return None


def _zip_member_parts(member_name: str) -> tuple[str, ...]:
    path = PurePosixPath(member_name.replace("\\", "/"))
    parts = tuple(part for part in path.parts if part not in {"", "."})
    if not parts or any(part == ".." for part in parts):
        raise RuntimeError(f"unsafe zip member path: {member_name}")
    return parts


def _zip_member_target(member_name: str, strip_prefix: str | None) -> Path | None:
    parts = _zip_member_parts(member_name)
    if strip_prefix and len(parts) > 1 and parts[0] == strip_prefix:
        parts = parts[1:]
    if not parts:
        return None
    return Path(*parts)


def _verify_entry(entry: ModelEntry) -> dict[str, Any]:
    source = entry.source
    source_type = source.get("type")

    if source_type == "url_zip":
        required_files = source.get("required_files_anywhere", [])
        required_exts = source.get("required_extensions_anywhere", [])
        if not isinstance(required_files, list) or not all(isinstance(item, str) for item in required_files):
            raise ValueError(
                f"model '{entry.name}' has invalid required_files_anywhere metadata for url_zip source"
            )
        if not isinstance(required_exts, list) or not all(isinstance(item, str) for item in required_exts):
            raise ValueError(
                f"model '{entry.name}' has invalid required_extensions_anywhere metadata for url_zip source"
            )

        discovered_files = [
            path for path in entry.local_path.rglob("*") if path.is_file() and path.stat().st_size > 0
        ]
        discovered_names = {path.name for path in discovered_files}
        discovered_exts = {path.suffix.lower() for path in discovered_files}

        missing: list[str] = []
        for file_name in required_files:
            if file_name not in discovered_names:
                missing.append(file_name)
        for ext in required_exts:
            normalized = ext.lower()
            if normalized not in discovered_exts:
                missing.append(f"*{normalized}")

        present = sorted(str(path.relative_to(entry.local_path)).replace("\\", "/") for path in discovered_files)
        try:
            local_path_rel = str(entry.local_path.relative_to(REPO_ROOT))
        except ValueError:
            local_path_rel = str(entry.local_path)
        return {
            "family": entry.family,
            "model": entry.name,
            "local_path": local_path_rel,
            "present": present,
            "missing": missing,
            "ready": not missing,
            "degraded_reason": _missing_artifact_reason(entry, missing),
        }

    missing: list[str] = []
    present: list[str] = []
    for file_name, _source_ref in _source_files(entry):
        target = _target_for_file(entry, file_name)
        if target.exists() and target.is_file() and target.stat().st_size > 0:
            present.append(file_name)
        else:
            missing.append(file_name)

    return {
        "family": entry.family,
        "model": entry.name,
        "local_path": _relative_local_path(entry.local_path),
        "present": present,
        "missing": missing,
        "ready": not missing,
        "degraded_reason": _missing_artifact_reason(entry, missing),
    }


def _verify_family(
    family: str,
    model_name: str | None = None,
    hardware_profile: HardwareProfile | None = None,
    extras: list[str] | None = None,
    llm_policy: str | None = None,
    all_llm: bool = False,
) -> tuple[int, dict[str, Any]]:
    selected_default = False
    if model_name:
        entries = [get_model_entry(family, model_name)]
        selected_policy: str | None = None
    elif family == "llm" and not all_llm and hardware_profile is not None:
        selection = select_llm_model("voice_chat", hardware_profile, policy=llm_policy)
        entries = [get_model_entry(family, selection.model_id)]
        selected_policy = selection.policy
        selected_default = True
    else:
        entries = [ModelEntry(family=family, name=name, config=config) for name, config in list_models(family).items()]
        selected_policy = None

    results = [_verify_entry(entry) for entry in entries]
    runtime_results = [
        _verify_runtime_artifacts(
            entry,
            hardware_profile=hardware_profile,
            extras=extras,
            current_host_only=selected_default,
        )
        for entry in entries
    ] if family == "llm" else []
    payload = {
        "family": family,
        "models": results,
        "runtime_artifacts": runtime_results,
        "ready": all(result["ready"] for result in results),
    }
    if family == "llm" and selected_policy is not None:
        payload["selection"] = {"policy": selected_policy, "model": entries[0].name}
    return (0 if all(result["ready"] for result in results) else 1), payload


def _download_huggingface(entry: ModelEntry, dry_run: bool) -> list[str]:
    source = entry.source
    repo_id = source.get("repo_id")
    subfolder = source.get("subfolder")
    if not isinstance(repo_id, str) or not repo_id:
        raise ValueError(f"model '{entry.name}' is missing Hugging Face repo_id")

    acquired: list[str] = []
    if not dry_run:
        target_root = entry.local_path.parent if _entry_targets_single_file(entry) else entry.local_path
        target_root.mkdir(parents=True, exist_ok=True)

    for file_name, source_ref in _source_files(entry):
        if source_ref != file_name:
            repo_filename = source_ref
        elif isinstance(subfolder, str) and subfolder:
            repo_filename = f"{subfolder.strip('/')}/{file_name}"
        else:
            repo_filename = file_name
        target = _target_for_file(entry, file_name)
        if dry_run:
            acquired.append(file_name)
            continue
        downloaded = Path(hf_hub_download(repo_id=repo_id, filename=repo_filename))
        shutil.copyfile(downloaded, target)
        if target.stat().st_size <= 0:
            raise RuntimeError(f"downloaded zero-byte file: {target}")
        acquired.append(file_name)
    return acquired


def _download_urls(entry: ModelEntry, dry_run: bool) -> list[str]:
    acquired: list[str] = []
    if not dry_run:
        entry.local_path.mkdir(parents=True, exist_ok=True)

    with httpx.Client(follow_redirects=True, timeout=120.0) as client:
        for file_name, url in _source_files(entry):
            if not url.startswith("https://"):
                raise ValueError(f"model '{entry.name}' file '{file_name}' has invalid URL")
            target = entry.local_path / file_name
            if dry_run:
                acquired.append(file_name)
                continue
            with client.stream("GET", url) as response:
                response.raise_for_status()
                with target.open("wb") as stream:
                    for chunk in response.iter_bytes():
                        if chunk:
                            stream.write(chunk)
            if target.stat().st_size <= 0:
                raise RuntimeError(f"downloaded zero-byte file: {target}")
            acquired.append(file_name)
    return acquired


def _download_url_zip(entry: ModelEntry, dry_run: bool) -> list[str]:
    source = entry.source
    url = source.get("url")
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError(f"model '{entry.name}' has invalid url for url_zip source")

    if dry_run:
        required_files = source.get("required_files_anywhere", [])
        if isinstance(required_files, list) and required_files:
            return [str(item) for item in required_files if isinstance(item, str)]
        return ["<archive-extracted>"]

    entry.local_path.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=300.0) as client:
        response = client.get(url)
        response.raise_for_status()
        payload = response.content

    extracted: list[str] = []
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for member in archive.infolist():
            archive.extract(member, path=entry.local_path)
            if member.is_dir():
                continue
            extracted.append(member.filename.replace("\\", "/"))

    if not extracted:
        raise RuntimeError(f"zip source for model '{entry.name}' extracted no files")
    return extracted


def _ensure_entry(entry: ModelEntry, dry_run: bool) -> dict[str, Any]:
    source_type = entry.source.get("type")
    if source_type == "huggingface":
        acquired = _download_huggingface(entry, dry_run)
    elif source_type == "url":
        acquired = _download_urls(entry, dry_run)
    elif source_type == "url_zip":
        acquired = _download_url_zip(entry, dry_run)
    else:
        raise ValueError(f"model '{entry.name}' has unsupported source type '{source_type}'")

    verify = {"ready": dry_run, "missing": [], "present": acquired}
    if not dry_run:
        verify = _verify_entry(entry)
    return {
        "family": entry.family,
        "model": entry.name,
        "dry_run": dry_run,
        "acquired": acquired,
        "ready": bool(verify["ready"]),
        "missing": verify["missing"],
    }


def _ensure_family(
    family: str,
    model_name: str | None,
    dry_run: bool,
    runtime_fetch_allowed: bool = True,
    runtime_fetch_reason: str = "explicit-cli",
    hardware_profile: HardwareProfile | None = None,
    extras: list[str] | None = None,
    llm_policy: str | None = None,
    all_llm: bool = False,
) -> tuple[int, dict[str, Any]]:
    selected_default = False
    if model_name:
        entries = [get_model_entry(family, model_name)]
        selected_policy: str | None = None
    elif family == "llm" and not all_llm and hardware_profile is not None:
        selection = select_llm_model("voice_chat", hardware_profile, policy=llm_policy)
        entries = [get_model_entry(family, selection.model_id)]
        selected_policy = selection.policy
        selected_default = True
    else:
        entries = [ModelEntry(family=family, name=name, config=config) for name, config in list_models(family).items()]
        selected_policy = None

    results = [_ensure_entry(entry, dry_run) for entry in entries]
    runtime_results: list[dict[str, Any]] = []
    if family == "llm":
        if runtime_fetch_allowed:
            runtime_results = [
                _ensure_runtime_artifacts(
                    entry,
                    dry_run=dry_run,
                    hardware_profile=hardware_profile,
                    extras=extras,
                    current_host_only=selected_default,
                )
                for entry in entries
            ]
        else:
            runtime_results = [
                {
                    "model": entry.name,
                    "profiles": [],
                    "ready": False,
                    "state": "skipped",
                    "degraded_reason": runtime_fetch_reason,
                }
                for entry in entries
            ]
    payload = {
        "family": family,
        "models": results,
        "runtime_artifacts": runtime_results,
        "ready": all(result["ready"] for result in results),
    }
    if family == "llm" and selected_policy is not None:
        payload["selection"] = {"policy": selected_policy, "model": entries[0].name}
    return (0 if all(result["ready"] for result in results) else 1), payload


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    configure_logging(level="DEBUG" if args.verbose else "INFO", trace_to=args.trace_to)
    profiler = _load_profiler()
    report = profiler()
    extras = resolve_required_extras(report.profile)
    emit_host_fingerprint(report.profile, extras, readiness="models")

    families = [args.family] if args.family else list(ALL_FAMILIES)
    runtime_fetch_allowed, runtime_fetch_reason = _runtime_fetch_allowed(args)
    exit_code = 0
    results: list[dict[str, Any]] = []
    for family in families:
        if args.verify_only:
            code, result = _verify_family(
                family,
                args.model,
                hardware_profile=report.profile,
                extras=extras,
                llm_policy=args.llm_policy,
                all_llm=args.all_llm,
            )
        else:
            code, result = _ensure_family(
                family,
                args.model,
                args.dry_run,
                runtime_fetch_allowed=runtime_fetch_allowed,
                runtime_fetch_reason=runtime_fetch_reason,
                hardware_profile=report.profile,
                extras=extras,
                llm_policy=args.llm_policy,
                all_llm=args.all_llm,
            )
        exit_code = max(exit_code, code)
        results.append(result)

    print(json.dumps({"families": results, "ready": exit_code == 0}, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
