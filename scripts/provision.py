from __future__ import annotations

import argparse
import importlib.metadata
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.core.logging import configure_logging, emit_host_fingerprint
from backend.app.core.paths import REPO_ROOT as APP_REPO_ROOT
from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.provisioning import (
    explain_required_extras,
    resolve_required_extras,
)


REQUIREMENTS_PATH = APP_REPO_ROOT / "backend" / "requirements.txt"


def _load_profiler():
    from backend.app.hardware.profiler import run_profiler

    return run_profiler


def _current_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_base_requirements() -> list[str]:
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python 3.11 always has tomllib
        return []

    pyproject_path = APP_REPO_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    dependencies = data.get("project", {}).get("dependencies", [])
    return [str(item).strip() for item in dependencies if str(item).strip()]


def _read_extra_requirements(extra: str) -> list[str]:
    try:
        import tomllib
    except ImportError:  # pragma: no cover - Python 3.11 always has tomllib
        return []

    pyproject_path = APP_REPO_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    optional_dependencies = data.get("project", {}).get("optional-dependencies", {})
    dependencies = optional_dependencies.get(extra, [])
    return [str(item).strip() for item in dependencies if str(item).strip()]


def _installed_distribution_names() -> set[str]:
    return set(_installed_distribution_versions())


def _installed_distribution_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        metadata = distribution.metadata
        name = metadata.get("Name")
        if name:
            versions[_canonicalize_package_name(str(name))] = distribution.version
    return versions


def _canonicalize_package_name(name: str) -> str:
    return name.strip().lower().replace("-", "_").replace(".", "_")


def _normalize_requirement_name(requirement: str) -> str:
    candidate = requirement.split(";", 1)[0].strip()
    if "[" in candidate:
        candidate = candidate.split("[", 1)[0]
    for separator in ("<", ">", "=", "!", " "):
        if separator in candidate:
            candidate = candidate.split(separator, 1)[0]
    return _canonicalize_package_name(candidate)


def _marker_environment(profile: HardwareProfile) -> dict[str, str]:
    try:
        from packaging.markers import default_environment
    except ImportError:
        from pip._vendor.packaging.markers import default_environment

    environment = default_environment()
    environment.update(
        {
            "sys_platform": {"windows": "win32", "linux": "linux", "darwin": "darwin"}.get(
                profile.os_name, profile.os_name
            ),
            "platform_system": {
                "windows": "Windows",
                "linux": "Linux",
                "darwin": "Darwin",
            }.get(profile.os_name, profile.os_name),
            "platform_machine": {
                ("windows", "amd64"): "AMD64",
                ("windows", "arm64"): "ARM64",
                ("linux", "amd64"): "x86_64",
                ("linux", "arm64"): "aarch64",
            }.get((profile.os_name, profile.arch), profile.arch),
        }
    )
    return environment


def _requirement_applies_to_profile(requirement: str, profile: HardwareProfile) -> bool:
    _specifier, separator, marker = requirement.partition(";")
    if not separator:
        return True
    try:
        from packaging.markers import Marker
    except ImportError:
        from pip._vendor.packaging.markers import Marker

    return Marker(marker.strip()).evaluate(_marker_environment(profile))


def _selected_requirement_specs(profile: HardwareProfile, include_porcupine: bool) -> list[str]:
    extras = resolve_required_extras(profile, include_porcupine=include_porcupine)
    return [
        requirement
        for requirement in [
            *_read_base_requirements(),
            *(requirement for extra in extras for requirement in _read_extra_requirements(extra)),
        ]
        if _requirement_applies_to_profile(requirement, profile)
    ]


def _exact_requirement_version(requirement: str) -> tuple[str, str] | None:
    candidate = requirement.split(";", 1)[0].strip()
    if "==" not in candidate:
        return None
    name, version = candidate.split("==", 1)
    if "[" in name:
        name = name.split("[", 1)[0]
    normalized_name = _canonicalize_package_name(name)
    expected_version = version.strip()
    if not normalized_name or not expected_version:
        return None
    return normalized_name, expected_version


def _build_pip_install_command(extras: list[str], include_porcupine: bool = False) -> list[str]:
    resolved_extras = list(extras)
    if include_porcupine and "hw-wake-porcupine" not in resolved_extras:
        resolved_extras.insert(-1, "hw-wake-porcupine")
    extras_spec = ",".join(resolved_extras)
    return [sys.executable, "-m", "pip", "install", "-e", f".[{extras_spec}]"]


def _write_requirements_lockfile(path: Path | None = None) -> None:
    if path is None:
        path = REQUIREMENTS_PATH
    lines = [
        f"# Generated by scripts/provision.py lock at {_current_timestamp()}",
        "# Base extra only. Do not edit by hand.",
        "",
    ]
    lines.extend(_read_base_requirements())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _emit_plan(
    profile: HardwareProfile,
    extras: list[str],
    include_porcupine: bool,
    out=None,
) -> None:
    if out is None:
        out = sys.stdout
    emit_host_fingerprint(profile, extras, out=out)
    for extra, reason in explain_required_extras(profile, include_porcupine):
        print(f"{extra}: {reason}", file=out)


def _run_pip_install(command: list[str]) -> int:
    completed = subprocess.run(command, check=False)
    return completed.returncode


def _parse_args(argv: list[str]) -> argparse.Namespace:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument("--verbose", action="store_true")
    shared.add_argument("--dry-run", action="store_true")
    shared.add_argument("--trace-to")
    shared.add_argument("--profile", action="store_true")

    parser = argparse.ArgumentParser(prog="provision.py", parents=[shared])
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", parents=[shared])
    install.add_argument("--with-porcupine", action="store_true")

    verify = subparsers.add_parser("verify", parents=[shared])
    verify.add_argument("--with-porcupine", action="store_true")

    dry_run = subparsers.add_parser("dry-run", parents=[shared])
    dry_run.add_argument("--with-porcupine", action="store_true")

    explain = subparsers.add_parser("explain", parents=[shared])
    explain.add_argument("--with-porcupine", action="store_true")

    subparsers.add_parser("lock", parents=[shared])
    return parser.parse_args(argv)


def _provision_context(include_porcupine: bool) -> tuple[HardwareProfile, list[str]]:
    profiler = _load_profiler()
    report = profiler()
    extras = resolve_required_extras(report.profile, include_porcupine=include_porcupine)
    return report.profile, extras


def _expected_distribution_names(profile: HardwareProfile, include_porcupine: bool) -> set[str]:
    return {
        _normalize_requirement_name(requirement)
        for requirement in _selected_requirement_specs(profile, include_porcupine)
        if _normalize_requirement_name(requirement)
    }


def _expected_exact_distribution_versions(
    profile: HardwareProfile,
    include_porcupine: bool,
) -> dict[str, str]:
    expected: dict[str, str] = {}
    for requirement in _selected_requirement_specs(profile, include_porcupine):
        exact = _exact_requirement_version(requirement)
        if exact is None:
            continue
        name, version = exact
        expected[name] = version
    return expected


def _run_install(profile: HardwareProfile, extras: list[str], include_porcupine: bool) -> int:
    command = _build_pip_install_command(extras, include_porcupine=include_porcupine)
    install_rc = _run_pip_install(command)
    if install_rc != 0:
        return install_rc

    cuda_profile = (
        profile.arch == "amd64"
        and profile.gpu_available
        and profile.gpu_vendor == "nvidia"
        and profile.cuda_available
    )
    if not cuda_profile:
        return 0

    uninstall_cpu_ort = [sys.executable, "-m", "pip", "uninstall", "-y", "onnxruntime"]
    uninstall_rc = _run_pip_install(uninstall_cpu_ort)
    if uninstall_rc != 0:
        return uninstall_rc

    reinstall_gpu_ort = [sys.executable, "-m", "pip", "install", "--force-reinstall", "onnxruntime-gpu>=1.17"]
    return _run_pip_install(reinstall_gpu_ort)


def _run_verify(profile: HardwareProfile, extras: list[str], include_porcupine: bool) -> int:
    expected_requirements = _expected_distribution_names(
        profile,
        include_porcupine=include_porcupine,
    )
    expected_versions = _expected_exact_distribution_versions(
        profile,
        include_porcupine=include_porcupine,
    )
    installed_versions = _installed_distribution_versions()
    installed_requirements = set(installed_versions)
    missing = sorted(expected_requirements - installed_requirements)
    version_mismatches = sorted(
        (
            name,
            expected_version,
            installed_versions.get(name, "<missing>"),
        )
        for name, expected_version in expected_versions.items()
        if name in installed_versions and installed_versions[name] != expected_version
    )
    unexpected = sorted(installed_requirements & expected_requirements)
    print(f"expected_requirements={sorted(expected_requirements)}")
    if expected_versions:
        print(f"expected_versions={dict(sorted(expected_versions.items()))}")
    print(f"installed_requirements={sorted(installed_requirements)}")
    if missing:
        print(f"missing={missing}")
    if version_mismatches:
        print(f"version_mismatches={version_mismatches}")
    if unexpected:
        print(f"present={unexpected}")
    return 0 if not missing and not version_mismatches else 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    configure_logging(level="DEBUG" if args.verbose else "INFO", trace_to=args.trace_to)

    if args.command == "lock":
        profile, extras = _provision_context(include_porcupine=False)
        emit_host_fingerprint(profile, extras)
        _write_requirements_lockfile()
        print(f"wrote {REQUIREMENTS_PATH}")
        return 0

    include_porcupine = bool(getattr(args, "with_porcupine", False))
    profile, extras = _provision_context(include_porcupine=include_porcupine)
    emit_host_fingerprint(profile, extras, readiness="not-checked")

    if args.command == "explain":
        for extra, reason in explain_required_extras(profile, include_porcupine=include_porcupine):
            print(f"{extra}: {reason}")
        return 0

    if args.command == "dry-run":
        command = _build_pip_install_command(extras, include_porcupine=include_porcupine)
        print(" ".join(command))
        for extra, reason in explain_required_extras(profile, include_porcupine=include_porcupine):
            print(f"{extra}: {reason}")
        return 0

    if args.command == "verify":
        return _run_verify(profile, extras, include_porcupine=include_porcupine)

    if args.command == "install":
        command = _build_pip_install_command(extras, include_porcupine=include_porcupine)
        print(" ".join(command))
        if args.dry_run:
            return 0
        return _run_install(profile, extras, include_porcupine=include_porcupine)

    raise ValueError(f"unsupported command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
