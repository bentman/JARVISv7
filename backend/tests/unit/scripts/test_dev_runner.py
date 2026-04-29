from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from scripts import dev_runner


def test_parse_args_accepts_check_arch_modes_and_shared_flags(tmp_path) -> None:
    args = dev_runner._parse_args(["--verbose", "--dry-run", "--trace-to", str(tmp_path), "check", "--arch", "x64-arm64"])
    assert args.verbose is True
    assert args.dry_run is True
    assert args.trace_to == tmp_path
    assert args.command == "check"
    assert args.arch == "x64-arm64"


def test_fingerprint_is_first_stdout_line_for_dry_run(monkeypatch, capsys) -> None:
    monkeypatch.setattr(dev_runner.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(dev_runner.platform, "python_version", lambda: "3.12.10")
    exit_code = dev_runner.main(["--dry-run", "check", "--arch", "x64"])
    output = capsys.readouterr().out.splitlines()
    assert exit_code == 0
    assert output[0].startswith("[fingerprint] arch=x64 python=3.12.10")


def test_arch_mappings_are_correct() -> None:
    assert dev_runner.ARCH_SPECS["x64"].rust_target == "x86_64-pc-windows-msvc"
    assert dev_runner.ARCH_SPECS["x64"].vcvars_arg == "amd64"
    assert dev_runner.ARCH_SPECS["x64"].expected_target_arch == "x64"
    assert dev_runner.ARCH_SPECS["arm64"].rust_target == "aarch64-pc-windows-msvc"
    assert dev_runner.ARCH_SPECS["arm64"].vcvars_arg == "arm64"
    assert dev_runner.ARCH_SPECS["arm64"].expected_target_arch == "arm64"
    assert dev_runner.ARCH_SPECS["x64-arm64"].rust_target == "aarch64-pc-windows-msvc"
    assert dev_runner.ARCH_SPECS["x64-arm64"].vcvars_arg == "amd64_arm64"
    assert dev_runner.ARCH_SPECS["x64-arm64"].expected_target_arch == "arm64"


def test_native_and_cross_arch_mismatch_rules_use_named_failure(monkeypatch) -> None:
    monkeypatch.setattr(dev_runner.platform, "machine", lambda: "AMD64")
    arm64_result = dev_runner._check_python_arch(dev_runner.ARCH_SPECS["arm64"])
    assert arm64_result.status == "FAIL"
    assert arm64_result.code == "python-arch-mismatch"

    monkeypatch.setattr(dev_runner.platform, "machine", lambda: "ARM64")
    cross_result = dev_runner._check_python_arch(dev_runner.ARCH_SPECS["x64-arm64"])
    assert cross_result.status == "FAIL"
    assert cross_result.code == "python-arch-mismatch"


def test_vswhere_path_preferred_when_available(monkeypatch) -> None:
    monkeypatch.setattr(dev_runner.shutil, "which", lambda name: r"C:\Tools\vswhere.exe" if name == "vswhere" else None)
    assert dev_runner._find_vswhere() == Path(r"C:\Tools\vswhere.exe")


def test_vswhere_canonical_fallback_used_when_not_on_path(monkeypatch) -> None:
    monkeypatch.setattr(dev_runner.shutil, "which", lambda name: None)
    monkeypatch.setattr(dev_runner.Path, "exists", lambda self: str(self).endswith("vswhere.exe"))
    assert str(dev_runner._find_vswhere()).endswith("vswhere.exe")


def test_vswhere_json_filters_to_instances_with_vcvarsall(monkeypatch) -> None:
    payload = [
        {"installationPath": r"C:\VS\NoTools", "displayName": "No Tools", "installationVersion": "18.0"},
        {"installationPath": r"C:\VS\Community", "displayName": "Community", "installationVersion": "18.1"},
    ]
    monkeypatch.setattr(dev_runner, "_run_command", lambda args, **kwargs: dev_runner.CommandResult(args, 0, dev_runner.json.dumps(payload), ""))
    monkeypatch.setattr(dev_runner.Path, "exists", lambda self: "Community" in str(self))
    candidates = dev_runner._candidate_installs_from_vswhere(Path("vswhere.exe"))
    assert len(candidates) == 1
    assert candidates[0].installation_path == Path(r"C:\VS\Community")


def test_fallback_discovery_supports_vs_2026_community_and_2022_buildtools(monkeypatch) -> None:
    class FakePath:
        def __init__(self, value: str) -> None:
            self.value = value
            self.name = value.rstrip("\\").split("\\")[-1]

        def __truediv__(self, other: str):
            return FakePath(self.value + "\\" + other)

        def exists(self) -> bool:
            return "Microsoft Visual Studio" in self.value or "vcvarsall.bat" in self.value

        def is_dir(self) -> bool:
            return True

        def iterdir(self):
            if self.value.endswith("Microsoft Visual Studio"):
                return iter([FakePath(self.value + r"\18"), FakePath(self.value + r"\2022")])
            if self.value.endswith("18"):
                return iter([FakePath(self.value + r"\Community")])
            if self.value.endswith("2022"):
                return iter([FakePath(self.value + r"\BuildTools")])
            return iter([])

        def __str__(self) -> str:
            return self.value

        def __repr__(self) -> str:
            return f"FakePath({self.value!r})"

    monkeypatch.setattr(dev_runner, "_visual_studio_roots", lambda: [FakePath(r"C:\Program Files\Microsoft Visual Studio")])
    candidates = dev_runner._candidate_installs_from_known_roots()
    assert any("18\\Community" in str(candidate.installation_path) for candidate in candidates)
    assert any("2022\\BuildTools" in str(candidate.installation_path) for candidate in candidates)


def test_vcvars_set_output_parser_extracts_required_env_keys() -> None:
    env = dev_runner._parse_set_output(
        "VSCMD_VER=17.14.30\nVSCMD_ARG_HOST_ARCH=x64\nVSCMD_ARG_TGT_ARCH=arm64\nPATH=C:\\bin\nINCLUDE=C:\\inc\nLIB=C:\\lib\nLIBPATH=C:\\libpath\n"
    )
    assert env["VSCMD_VER"] == "17.14.30"
    assert env["VSCMD_ARG_TGT_ARCH"] == "arm64"
    assert env["LIBPATH"] == "C:\\libpath"


def test_target_mismatch_reports_named_failure(monkeypatch) -> None:
    install = dev_runner.VsInstall(Path("C:/VS"), Path("C:/VS/VC/Auxiliary/Build/vcvarsall.bat"), "VS", "18", "test")
    stdout = "VSCMD_VER=1\nVSCMD_ARG_HOST_ARCH=x64\nVSCMD_ARG_TGT_ARCH=x64\nPATH=x\nINCLUDE=x\nLIB=x\nLIBPATH=x\n"
    monkeypatch.setattr(dev_runner.Path, "exists", lambda self: True)
    monkeypatch.setattr(dev_runner, "_run_command", lambda *args, **kwargs: dev_runner.CommandResult("cmd", 0, stdout, ""))
    result, _env = dev_runner._capture_vcvars_environment(install, dev_runner.ARCH_SPECS["x64-arm64"])
    assert result.status == "FAIL"
    assert result.code == "msvc-target-mismatch"


def test_where_cl_and_link_run_under_captured_env(monkeypatch) -> None:
    calls = []

    def fake_run(args, *, env=None, shell=False):
        calls.append((args, env, shell))
        return dev_runner.CommandResult(args, 0, r"C:\cl.exe\n", "")

    monkeypatch.setattr(dev_runner, "_run_command", fake_run)
    env = {"PATH": "captured"}
    assert dev_runner._check_where_tool("cl", "cl-missing", env).status == "PASS"
    assert calls[0][1] is env


def test_missing_rust_target_reports_fail_without_install(monkeypatch) -> None:
    monkeypatch.setattr(dev_runner, "_installed_rust_targets", lambda: ({"x86_64-pc-windows-msvc"}, "x86_64-pc-windows-msvc"))
    result = dev_runner._check_rust_target(dev_runner.ARCH_SPECS["x64-arm64"])
    assert result.status == "FAIL"
    assert result.code == "rust-target-missing"


def test_missing_pnpm_is_warn_only(monkeypatch) -> None:
    monkeypatch.setattr(dev_runner.shutil, "which", lambda name: None)
    result = dev_runner._check_pnpm()
    assert result.status == "WARN"
    assert result.code == "pnpm-missing"


def test_webview2_registry_pv_value_passes(monkeypatch) -> None:
    monkeypatch.setattr(dev_runner.platform, "system", lambda: "Windows")
    monkeypatch.setattr(dev_runner, "_registry_value", lambda root, subkey, value_name: "123.0")
    result = dev_runner._check_webview2()
    assert result.status == "PASS"
    assert result.code == "webview2"


def test_webview2_inconclusive_state_warns(monkeypatch) -> None:
    monkeypatch.setattr(dev_runner.platform, "system", lambda: "Windows")
    monkeypatch.setattr(dev_runner.platform, "release", lambda: "11")
    monkeypatch.setattr(dev_runner, "_registry_value", lambda root, subkey, value_name: None)
    result = dev_runner._check_webview2()
    assert result.status == "WARN"
    assert result.code == "webview2-uncertain"


def test_definitive_webview2_absence_can_fail(monkeypatch) -> None:
    monkeypatch.setattr(dev_runner.platform, "system", lambda: "Windows")
    monkeypatch.setattr(dev_runner.platform, "release", lambda: "8")
    monkeypatch.setattr(dev_runner, "_registry_value", lambda root, subkey, value_name: None)
    result = dev_runner._check_webview2()
    assert result.status == "FAIL"
    assert result.code == "webview2-missing"


def test_exit_code_zero_only_when_required_checks_pass(monkeypatch, capsys) -> None:
    monkeypatch.setattr(dev_runner.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(dev_runner.platform, "system", lambda: "Windows")
    monkeypatch.setattr(dev_runner.platform, "release", lambda: "11")
    monkeypatch.setattr(dev_runner, "_check_executable", lambda name, code: dev_runner._result(name, "PASS", name, "ok"))
    monkeypatch.setattr(dev_runner, "_check_rust_target", lambda spec: dev_runner._result("rust-target", "PASS", "rust-target", "ok"))
    monkeypatch.setattr(dev_runner, "_check_pnpm", lambda: dev_runner._result("pnpm", "WARN", "pnpm-missing", "optional"))
    monkeypatch.setattr(dev_runner, "_check_webview2", lambda: dev_runner._result("webview2", "WARN", "webview2-uncertain", "uncertain"))
    env = {"PATH": "x"}
    install = dev_runner.VsInstall(Path("C:/VS"), Path("C:/VS/vcvarsall.bat"), "VS", "18", "test")
    msvc = dev_runner.MsvcEnvironment(Path("C:/VS/vcvarsall.bat"), "amd64", env)
    monkeypatch.setattr(
        dev_runner,
        "_select_working_msvc_candidate",
        lambda spec, trace: (install, dev_runner._result("msvc-env", "PASS", "msvc-env", "ok"), msvc),
    )
    monkeypatch.setattr(dev_runner, "_check_where_tool", lambda tool, code, env: dev_runner._result(tool, "PASS", tool, "ok"))
    assert dev_runner.main(["check", "--arch", "x64"]) == 0
    capsys.readouterr()

    monkeypatch.setattr(dev_runner, "_check_rust_target", lambda spec: dev_runner._result("rust-target", "FAIL", "rust-target-missing", "missing"))
    assert dev_runner.main(["check", "--arch", "x64"]) == 1


def test_trace_to_writes_trace_output_when_requested(monkeypatch, capsys, tmp_path) -> None:
    monkeypatch.setattr(dev_runner.platform, "machine", lambda: "AMD64")
    monkeypatch.setattr(dev_runner, "_check_executable", lambda name, code: dev_runner._result(name, "PASS", name, "ok"))
    monkeypatch.setattr(dev_runner, "_check_rust_target", lambda spec: dev_runner._result("rust-target", "PASS", "rust-target", "ok"))
    monkeypatch.setattr(dev_runner, "_check_pnpm", lambda: dev_runner._result("pnpm", "WARN", "pnpm-missing", "optional"))
    monkeypatch.setattr(dev_runner, "_select_working_msvc_candidate", lambda spec, trace: (None, dev_runner._result("vs-install", "FAIL", "vs-install-missing", "missing"), None))
    monkeypatch.setattr(dev_runner, "_check_webview2", lambda: dev_runner._result("webview2", "WARN", "webview2-uncertain", "uncertain"))
    exit_code = dev_runner.main(["--trace-to", str(tmp_path), "check", "--arch", "x64"])
    capsys.readouterr()
    assert exit_code == 1
    traces = list(tmp_path.glob("*-dev-runner.txt"))
    assert len(traces) == 1
    assert "check arch=x64" in traces[0].read_text(encoding="utf-8")