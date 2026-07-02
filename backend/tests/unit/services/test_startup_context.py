from __future__ import annotations

from dataclasses import dataclass

from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.services import startup_context


@dataclass(slots=True)
class _Report:
    profile: HardwareProfile
    flags: CapabilityFlags


def _fake_report() -> _Report:
    return _Report(
        profile=HardwareProfile(arch="amd64", os_name="windows"),
        flags=CapabilityFlags(supports_local_stt=True),
    )


def _fake_preflight(*, probe_errors: dict[str, str] | None = None) -> PreflightResult:
    return PreflightResult(
        tokens=["import:onnxruntime", "import:kokoro_onnx"],
        dll_discovery_log=[],
        probe_errors=probe_errors or {},
    )


def test_load_profile_context_resolves_report_profile_and_extras(monkeypatch) -> None:
    report = _fake_report()
    monkeypatch.setattr(
        "backend.app.hardware.profiler.run_profiler",
        lambda: report,
    )
    monkeypatch.setattr(
        "backend.app.hardware.provisioning.resolve_required_extras",
        lambda profile: ["dev"],
    )

    context = startup_context.load_profile_context()

    assert context.report is report
    assert context.profile is report.profile
    assert context.extras == ["dev"]


def test_complete_startup_context_runs_preflight_and_derives_readiness(monkeypatch) -> None:
    report = _fake_report()
    profile_context = startup_context.ProfileContext(report=report, profile=report.profile, extras=["dev"])
    preflight = _fake_preflight()

    monkeypatch.setattr(
        "backend.app.hardware.preflight.run_preflight",
        lambda profile, extras: preflight,
    )
    monkeypatch.setattr(
        startup_context,
        "derive_readiness_map",
        lambda startup_preflight, profile: {"stt": ("cpu", True, "ready")},
    )

    context = startup_context.complete_startup_context(profile_context)

    assert context.report is report
    assert context.profile is report.profile
    assert context.extras == ["dev"]
    assert context.preflight is preflight
    assert context.readiness == {"stt": ("cpu", True, "ready")}


def test_readiness_summary_reports_probe_error_degradation() -> None:
    report = _fake_report()
    context = startup_context.StartupContext(
        report=report,
        profile=report.profile,
        extras=["dev"],
        preflight=_fake_preflight(probe_errors={"import:missing": "missing"}),
        readiness={},
    )

    assert startup_context.readiness_summary(context) == "degraded; tokens=2"


def test_selected_path_summary_preserves_qnn_probe_error_guard() -> None:
    report = _fake_report()
    context = startup_context.StartupContext(
        report=report,
        profile=report.profile,
        extras=["dev"],
        preflight=_fake_preflight(probe_errors={"onnxruntime.qnn.ep": "missing"}),
        readiness={
            "stt": ("qnn", True, "qnn selected"),
            "tts": ("cpu", True, "tts ready"),
            "wake": ("cpu", True, "wake ready"),
        },
    )

    assert startup_context.selected_path_readiness_summary(context) == "degraded; tokens=2"
