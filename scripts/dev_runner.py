from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

WEBVIEW2_RUNTIME_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"


@dataclass(frozen=True, slots=True)
class ArchSpec:
    name: str
    python_arches: tuple[str, ...]
    rust_target: str
    vcvars_arg: str
    expected_target_arch: str
    expected_host_arch: str


ARCH_SPECS: dict[str, ArchSpec] = {
    "x64": ArchSpec(
        name="x64",
        python_arches=("amd64", "x86_64"),
        rust_target="x86_64-pc-windows-msvc",
        vcvars_arg="amd64",
        expected_target_arch="x64",
        expected_host_arch="x64",
    ),
    "arm64": ArchSpec(
        name="arm64",
        python_arches=("arm64", "aarch64"),
        rust_target="aarch64-pc-windows-msvc",
        vcvars_arg="arm64",
        expected_target_arch="arm64",
        expected_host_arch="arm64",
    ),
    "x64-arm64": ArchSpec(
        name="x64-arm64",
        python_arches=("amd64", "x86_64"),
        rust_target="aarch64-pc-windows-msvc",
        vcvars_arg="amd64_arm64",
        expected_target_arch="arm64",
        expected_host_arch="x64",
    ),
}


@dataclass(slots=True)
class CommandResult:
    args: list[str] | str
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    status: str
    code: str
    message: str

    @property
    def is_failure(self) -> bool:
        return self.status == "FAIL"


@dataclass(frozen=True, slots=True)
class VsInstall:
    installation_path: Path
    vcvarsall_path: Path
    display_name: str
    installation_version: str
    source: str


@dataclass(slots=True)
class MsvcEnvironment:
    vcvarsall_path: Path
    vcvars_arg: str
    env: dict[str, str]

    @property
    def vscmd_ver(self) -> str:
        return self.env.get("VSCMD_VER", "")

    @property
    def host_arch(self) -> str:
        return self.env.get("VSCMD_ARG_HOST_ARCH", "")

    @property
    def target_arch(self) -> str:
        return self.env.get("VSCMD_ARG_TGT_ARCH", "")


class Trace:
    def __init__(self, trace_to: Path | None) -> None:
        self.path: Path | None = None
        self.lines: list[str] = []
        if trace_to is not None:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
            self.path = trace_to / f"{stamp}-dev-runner.txt"

    def add(self, line: str) -> None:
        self.lines.append(line)

    def write(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="dev_runner.py")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--trace-to", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--arch", choices=sorted(ARCH_SPECS), required=True)
    return parser.parse_args(argv)


def _normalize_python_arch(value: str | None = None) -> str:
    raw = (value or platform.machine()).lower()
    if raw in {"amd64", "x86_64"}:
        return "x64"
    if raw in {"arm64", "aarch64"}:
        return "arm64"
    return raw or "unknown"


def _emit_fingerprint(out: TextIO) -> None:
    print(
        "[fingerprint] "
        f"arch={_normalize_python_arch()} "
        f"python={platform.python_version()} "
        f"executable={sys.executable} "
        "readiness=dev-runner-check",
        file=out,
    )


def _result(name: str, status: str, code: str, message: str) -> CheckResult:
    return CheckResult(name=name, status=status, code=code, message=message)


def _print_result(result: CheckResult, out: TextIO, trace: Trace) -> None:
    line = f"{result.status}:{result.code} {result.name}: {result.message}"
    print(line, file=out)
    trace.add(line)


def _run_command(args: list[str] | str, *, env: dict[str, str] | None = None, shell: bool = False) -> CommandResult:
    try:
        completed = subprocess.run(
            args,
            cwd=REPO_ROOT,
            env=env,
            shell=shell,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        return CommandResult(args=args, returncode=1, stdout="", stderr=str(exc))
    return CommandResult(args=args, returncode=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)


def _check_python_arch(spec: ArchSpec) -> CheckResult:
    machine = platform.machine().lower()
    if machine not in spec.python_arches:
        return _result(
            "python-arch",
            "FAIL",
            "python-arch-mismatch",
            f"python arch {platform.machine()} is incompatible with --arch {spec.name}",
        )
    return _result("python-arch", "PASS", "python-arch", f"python arch {platform.machine()} accepted")


def _check_executable(name: str, failure_code: str) -> CheckResult:
    path = shutil.which(name)
    if not path:
        return _result(name, "FAIL", failure_code, f"{name} not found on PATH")
    version = _run_command([path, "--version"])
    if version.returncode != 0:
        return _result(name, "FAIL", failure_code, f"{name} --version failed")
    first_line = (version.stdout or version.stderr).splitlines()[0] if (version.stdout or version.stderr).splitlines() else path
    return _result(name, "PASS", name, first_line)


def _check_pnpm() -> CheckResult:
    path = shutil.which("pnpm")
    if not path:
        return _result("pnpm", "WARN", "pnpm-missing", "pnpm not found; optional and non-required")
    version = _run_command([path, "--version"])
    if version.returncode != 0:
        return _result("pnpm", "WARN", "pnpm-missing", "pnpm --version failed; optional and non-required")
    return _result("pnpm", "PASS", "pnpm", version.stdout.strip() or "present")


def _installed_rust_targets() -> tuple[set[str], str]:
    result = _run_command(["rustup", "target", "list", "--installed"])
    if result.returncode != 0:
        return set(), result.stderr.strip() or result.stdout.strip()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}, result.stdout.strip()


def _check_rust_target(spec: ArchSpec) -> CheckResult:
    targets, detail = _installed_rust_targets()
    if spec.rust_target not in targets:
        return _result(
            "rust-target",
            "FAIL",
            "rust-target-missing",
            f"required Rust target {spec.rust_target} not installed; installed={sorted(targets) or detail}",
        )
    return _result("rust-target", "PASS", "rust-target", f"{spec.rust_target} installed")


def _find_vswhere() -> Path | None:
    path = shutil.which("vswhere")
    if path:
        return Path(path)
    fallback = Path(r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe")
    if fallback.exists():
        return fallback
    return None


def _vs_install_from_path(path: Path, *, display_name: str, version: str, source: str) -> VsInstall | None:
    vcvars = path / "VC" / "Auxiliary" / "Build" / "vcvarsall.bat"
    if not vcvars.exists():
        return None
    return VsInstall(path, vcvars, display_name, version, source)


def _candidate_installs_from_vswhere(vswhere: Path) -> list[VsInstall]:
    result = _run_command([str(vswhere), "-all", "-products", "*", "-format", "json"])
    if result.returncode != 0:
        return []
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    candidates: list[VsInstall] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("isComplete") is False or item.get("isLaunchable") is False:
            continue
        install_path = item.get("installationPath")
        if not install_path:
            continue
        candidate = _vs_install_from_path(
            Path(install_path),
            display_name=str(item.get("displayName") or item.get("installationName") or install_path),
            version=str(item.get("installationVersion") or ""),
            source="vswhere",
        )
        if candidate is not None:
            candidates.append(candidate)
    return _sort_vs_candidates(candidates)


def _visual_studio_roots() -> list[Path]:
    roots: list[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if base:
            roots.append(Path(base) / "Microsoft Visual Studio")
    return roots


def _candidate_installs_from_known_roots() -> list[VsInstall]:
    editions = {"BuildTools", "Community", "Professional", "Enterprise"}
    candidates: list[VsInstall] = []
    for root in _visual_studio_roots():
        if not root.exists():
            continue
        for version_dir in sorted((p for p in root.iterdir() if p.is_dir()), key=lambda p: p.name):
            for edition_dir in sorted((p for p in version_dir.iterdir() if p.is_dir()), key=lambda p: p.name):
                if edition_dir.name not in editions:
                    continue
                candidate = _vs_install_from_path(
                    edition_dir,
                    display_name=f"Visual Studio {version_dir.name} {edition_dir.name}",
                    version=version_dir.name,
                    source="known-roots",
                )
                if candidate is not None:
                    candidates.append(candidate)
    return _sort_vs_candidates(candidates)


def _sort_vs_candidates(candidates: list[VsInstall]) -> list[VsInstall]:
    def key(candidate: VsInstall) -> tuple[tuple[int, ...], str]:
        parts: list[int] = []
        for part in candidate.installation_version.replace("+", ".").split("."):
            if part.isdigit():
                parts.append(int(part))
        return (tuple(parts), str(candidate.installation_path).lower())

    return sorted(candidates, key=key, reverse=True)


def _candidate_vs_installs() -> list[VsInstall]:
    vswhere = _find_vswhere()
    if vswhere is not None:
        candidates = _candidate_installs_from_vswhere(vswhere)
        if candidates:
            return candidates
    return _candidate_installs_from_known_roots()


def _parse_set_output(stdout: str) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in stdout.splitlines():
        if "=" not in line or line.startswith("[") or line.startswith("*"):
            continue
        key, value = line.split("=", 1)
        env[key.upper()] = value
    return env


def _capture_vcvars_environment(candidate: VsInstall, spec: ArchSpec) -> tuple[CheckResult, MsvcEnvironment | None]:
    if not candidate.vcvarsall_path.exists():
        return _result("vcvarsall", "FAIL", "vcvarsall-missing", str(candidate.vcvarsall_path)), None
    command = f'cmd /c ""{candidate.vcvarsall_path}" {spec.vcvars_arg} && set"'
    result = _run_command(command, shell=True)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit={result.returncode}"
        return _result("vcvarsall", "FAIL", "vcvarsall-failed", detail), None
    env = _parse_set_output(result.stdout)
    required = ["VSCMD_VER", "VSCMD_ARG_HOST_ARCH", "VSCMD_ARG_TGT_ARCH", "PATH", "INCLUDE", "LIB", "LIBPATH"]
    missing = [key for key in required if not env.get(key)]
    if missing:
        return _result("msvc-env", "FAIL", "msvc-env-missing", f"missing {missing}"), None
    msvc_env = MsvcEnvironment(candidate.vcvarsall_path, spec.vcvars_arg, env)
    if msvc_env.target_arch.lower() != spec.expected_target_arch:
        return (
            _result(
                "msvc-target",
                "FAIL",
                "msvc-target-mismatch",
                f"expected {spec.expected_target_arch}, got {msvc_env.target_arch}",
            ),
            msvc_env,
        )
    if msvc_env.host_arch.lower() != spec.expected_host_arch:
        return (
            _result(
                "msvc-host",
                "FAIL",
                "msvc-host-mismatch",
                f"expected {spec.expected_host_arch}, got {msvc_env.host_arch}",
            ),
            msvc_env,
        )
    return (
        _result(
            "msvc-env",
            "PASS",
            "msvc-env",
            f"VSCMD_VER={msvc_env.vscmd_ver} host={msvc_env.host_arch} target={msvc_env.target_arch}",
        ),
        msvc_env,
    )


def _check_where_tool(tool: str, failure_code: str, env: dict[str, str]) -> CheckResult:
    result = _run_command(["where", tool], env=env)
    if result.returncode != 0:
        return _result(tool, "FAIL", failure_code, result.stderr.strip() or result.stdout.strip() or f"{tool} not found")
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return _result(tool, "PASS", tool, lines[0] if lines else f"{tool} found")


def _registry_value(root, subkey: str, value_name: str) -> str | None:
    try:
        import winreg

        with winreg.OpenKey(root, subkey) as key:
            value, _kind = winreg.QueryValueEx(key, value_name)
            if isinstance(value, str) and value.strip():
                return value.strip()
    except (FileNotFoundError, OSError, ImportError):
        return None
    return None


def _check_webview2() -> CheckResult:
    if platform.system().lower() != "windows":
        return _result("webview2", "WARN", "webview2-uncertain", "non-Windows host; WebView2 registry unavailable")
    subkeys = [
        rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_RUNTIME_GUID}",
        rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_RUNTIME_GUID}",
    ]
    try:
        import winreg

        roots = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
    except ImportError:
        # _registry_value handles winreg unavailability itself; keep the probe
        # loop testable on non-Windows hosts.
        roots = [None, None]
    for root in roots:
        for subkey in subkeys:
            version = _registry_value(root, subkey, "pv")
            if version:
                return _result("webview2", "PASS", "webview2", f"runtime version {version}")
    if platform.release() in {"10", "11"}:
        return _result("webview2", "WARN", "webview2-uncertain", "runtime registry key not found; absence not definitive")
    return _result("webview2", "FAIL", "webview2-missing", "runtime registry key absent across implemented checks")


def _select_working_msvc_candidate(spec: ArchSpec, trace: Trace) -> tuple[VsInstall | None, CheckResult, MsvcEnvironment | None]:
    candidates = _candidate_vs_installs()
    if not candidates:
        return None, _result("vs-install", "FAIL", "vs-install-missing", "no usable Visual Studio install with vcvarsall.bat"), None
    last_result: CheckResult | None = None
    last_env: MsvcEnvironment | None = None
    for candidate in candidates:
        trace.add(f"candidate-vs path={candidate.installation_path} source={candidate.source}")
        result, env = _capture_vcvars_environment(candidate, spec)
        if result.status == "PASS":
            return candidate, result, env
        last_result = result
        last_env = env
    return candidates[0], last_result or _result("vcvarsall", "FAIL", "vcvarsall-failed", "no candidate succeeded"), last_env


def _run_check(args: argparse.Namespace, out: TextIO) -> int:
    spec = ARCH_SPECS[args.arch]
    trace = Trace(args.trace_to)
    results: list[CheckResult] = []

    _emit_fingerprint(out)
    trace.add(f"check arch={args.arch} dry_run={args.dry_run}")

    if args.dry_run:
        print(
            f"dry-run arch={spec.name} rust_target={spec.rust_target} vcvars_arg={spec.vcvars_arg} expected_target={spec.expected_target_arch}",
            file=out,
        )
        trace.write()
        return 0

    for result in [
        _check_python_arch(spec),
        _check_executable("node", "node-missing"),
        _check_executable("npm", "npm-missing"),
        _check_executable("rustc", "rust-missing"),
        _check_executable("cargo", "cargo-missing"),
        _check_rust_target(spec),
        _check_pnpm(),
    ]:
        results.append(result)
        _print_result(result, out, trace)

    candidate, msvc_result, msvc_env = _select_working_msvc_candidate(spec, trace)
    if candidate is None:
        results.append(msvc_result)
        _print_result(msvc_result, out, trace)
    else:
        vs_result = _result(
            "vs-install",
            "PASS",
            "vs-install",
            f"{candidate.installation_path} source={candidate.source}",
        )
        results.append(vs_result)
        _print_result(vs_result, out, trace)
        results.append(msvc_result)
        _print_result(msvc_result, out, trace)
        if msvc_env is not None:
            for tool_result in [
                _check_where_tool("cl", "cl-missing", msvc_env.env),
                _check_where_tool("link", "link-missing", msvc_env.env),
            ]:
                results.append(tool_result)
                _print_result(tool_result, out, trace)

    webview2 = _check_webview2()
    results.append(webview2)
    _print_result(webview2, out, trace)

    failures = [result for result in results if result.is_failure]
    warnings = [result for result in results if result.status == "WARN"]
    print(f"SUMMARY arch={spec.name} failures={len(failures)} warnings={len(warnings)}", file=out)
    trace.add(f"summary failures={len(failures)} warnings={len(warnings)}")
    trace.write()
    return 1 if failures else 0


def main(argv: list[str] | None = None, out: TextIO | None = None) -> int:
    output = out or sys.stdout
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "check":
        return _run_check(args, output)
    return 3


if __name__ == "__main__":
    raise SystemExit(main())