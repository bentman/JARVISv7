from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from scripts import run_backend


@dataclass(slots=True)
class _Report:
    profile: HardwareProfile
    flags: CapabilityFlags


def _fake_report() -> _Report:
    return _Report(
        profile=HardwareProfile(
            os_name="windows",
            arch="amd64",
            profile_id="profile-test",
            profiled_at="2026-04-28T00:00:00Z",
        ),
        flags=CapabilityFlags(),
    )


def _patch_startup(monkeypatch) -> None:
    monkeypatch.setattr(run_backend, "run_profiler", lambda: _fake_report())
    monkeypatch.setattr(run_backend, "resolve_required_extras", lambda profile: ["dev"])
    monkeypatch.setattr(
        run_backend,
        "run_preflight",
        lambda profile, extras: PreflightResult(tokens=["import:onnxruntime"], dll_discovery_log=[], probe_errors={}),
    )


def test_parse_args_accepts_host_port_reload_and_shared_flags() -> None:
    args = run_backend._parse_args(
        ["--host", "127.0.0.1", "--port", "8765", "--reload", "--verbose", "--dry-run"]
    )
    assert args.host == "127.0.0.1"
    assert args.port == 8765
    assert args.reload is True
    assert args.verbose is True
    assert args.dry_run is True


def test_dry_run_emits_fingerprint_first(monkeypatch, capsys) -> None:
    _patch_startup(monkeypatch)
    exit_code = run_backend.main(["--dry-run", "--host", "127.0.0.1", "--port", "8765"])
    output = capsys.readouterr().out.splitlines()
    assert exit_code == 0
    assert output[0].startswith("[fingerprint]")
    assert output[1] == "run_backend dry-run host=127.0.0.1 port=8765 reload=False"


def test_dry_run_does_not_start_uvicorn(monkeypatch) -> None:
    _patch_startup(monkeypatch)
    called = []
    monkeypatch.setitem(__import__("sys").modules, "uvicorn", type("U", (), {"run": lambda *a, **k: called.append(True)}))
    exit_code = run_backend.main(["--dry-run"])
    assert exit_code == 0
    assert called == []