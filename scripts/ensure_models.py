from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

import httpx
from huggingface_hub import hf_hub_download

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.logging import configure_logging, emit_host_fingerprint
from backend.app.models.catalog import ModelEntry, get_model_entry, list_models
from backend.app.hardware.provisioning import resolve_required_extras

MODEL_FAMILIES = ("stt", "tts", "wake")
ALL_FAMILIES = (*MODEL_FAMILIES, "llm")


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
    return parser.parse_args(argv)


def _source_files(entry: ModelEntry) -> list[tuple[str, str]]:
    source = entry.source
    files = source.get("files", [])
    if isinstance(files, list):
        return [(str(file_name), str(file_name)) for file_name in files]
    if isinstance(files, dict):
        return [(str(file_name), str(source_ref)) for file_name, source_ref in files.items()]
    raise ValueError(f"model '{entry.name}' has invalid source files metadata")


def _verify_entry(entry: ModelEntry) -> dict[str, Any]:
    missing: list[str] = []
    present: list[str] = []
    for file_name, _source_ref in _source_files(entry):
        target = entry.local_path / file_name
        if target.exists() and target.is_file() and target.stat().st_size > 0:
            present.append(file_name)
        else:
            missing.append(file_name)

    return {
        "family": entry.family,
        "model": entry.name,
        "local_path": str(entry.local_path.relative_to(REPO_ROOT)),
        "present": present,
        "missing": missing,
        "ready": not missing,
    }


def _verify_family(family: str, model_name: str | None = None) -> tuple[int, dict[str, Any]]:
    if family == "llm":
        return 0, {"family": "llm", "ready": True, "status": "ollama_manages_models"}

    if model_name:
        entries = [get_model_entry(family, model_name)]
    else:
        entries = [ModelEntry(family=family, name=name, config=config) for name, config in list_models(family).items()]

    results = [_verify_entry(entry) for entry in entries]
    return (0 if all(result["ready"] for result in results) else 1), {
        "family": family,
        "models": results,
        "ready": all(result["ready"] for result in results),
    }


def _download_huggingface(entry: ModelEntry, dry_run: bool) -> list[str]:
    source = entry.source
    repo_id = source.get("repo_id")
    subfolder = source.get("subfolder")
    if not isinstance(repo_id, str) or not repo_id:
        raise ValueError(f"model '{entry.name}' is missing Hugging Face repo_id")

    acquired: list[str] = []
    if not dry_run:
        entry.local_path.mkdir(parents=True, exist_ok=True)

    for file_name, _source_ref in _source_files(entry):
        repo_filename = f"{subfolder.strip('/')}/{file_name}" if isinstance(subfolder, str) and subfolder else file_name
        target = entry.local_path / file_name
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


def _ensure_entry(entry: ModelEntry, dry_run: bool) -> dict[str, Any]:
    source_type = entry.source.get("type")
    if source_type == "huggingface":
        acquired = _download_huggingface(entry, dry_run)
    elif source_type == "url":
        acquired = _download_urls(entry, dry_run)
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


def _ensure_family(family: str, model_name: str | None, dry_run: bool) -> tuple[int, dict[str, Any]]:
    if family == "llm":
        return 0, {"family": "llm", "status": "ollama_manages_models", "ready": True}

    if model_name:
        entries = [get_model_entry(family, model_name)]
    else:
        entries = [ModelEntry(family=family, name=name, config=config) for name, config in list_models(family).items()]

    results = [_ensure_entry(entry, dry_run) for entry in entries]
    return (0 if all(result["ready"] for result in results) else 1), {
        "family": family,
        "models": results,
        "ready": all(result["ready"] for result in results),
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    configure_logging(level="DEBUG" if args.verbose else "INFO", trace_to=args.trace_to)
    profiler = _load_profiler()
    report = profiler()
    extras = resolve_required_extras(report.profile)
    emit_host_fingerprint(report.profile, extras, readiness="models")

    families = [args.family] if args.family else list(ALL_FAMILIES)
    exit_code = 0
    results: list[dict[str, Any]] = []
    for family in families:
        if args.verify_only:
            code, result = _verify_family(family, args.model)
        else:
            code, result = _ensure_family(family, args.model, args.dry_run)
        exit_code = max(exit_code, code)
        results.append(result)

    print(json.dumps({"families": results, "ready": exit_code == 0}, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
