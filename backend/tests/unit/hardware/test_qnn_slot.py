from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware import preflight as preflight_module
from backend.app.hardware.preflight import PreflightResult
from backend.app.hardware.profiler import derive_capability_flags
from backend.app.hardware.provisioning import resolve_required_extras
from backend.app.hardware.readiness import derive_stt_device_readiness


def _profile(**overrides) -> HardwareProfile:
    return HardwareProfile(**overrides)


def _preflight(*tokens: str) -> PreflightResult:
    return PreflightResult(tokens=list(tokens), dll_discovery_log=[], probe_errors={})


def test_qnn_available_flag_true_for_qualcomm_npu_host() -> None:
    flags = derive_capability_flags(
        _profile(
            os_name="windows",
            arch="arm64",
            cpu_physical_cores=8,
            memory_total_gb=16.0,
            npu_available=True,
            npu_vendor="qualcomm",
        )
    )

    assert flags.qnn_available is True


def test_qnn_available_flag_false_for_non_qualcomm_npu_host() -> None:
    flags = derive_capability_flags(
        _profile(
            os_name="windows",
            arch="arm64",
            cpu_physical_cores=8,
            memory_total_gb=16.0,
            npu_available=True,
            npu_vendor="intel",
        )
    )

    assert flags.qnn_available is False


def test_resolver_returns_qnn_extra_for_qualcomm_host() -> None:
    extras = resolve_required_extras(
        _profile(
            os_name="windows",
            arch="arm64",
            npu_available=True,
            npu_vendor="qualcomm",
        )
    )

    assert "hw-npu-qualcomm-qnn" in extras


def test_preflight_emits_qnn_import_token_when_package_installed(monkeypatch) -> None:
    preflight_module._CACHE.clear()
    monkeypatch.setattr(preflight_module, "_bootstrap_windows_dlls", lambda profile, tokens, log: None)
    monkeypatch.setattr(
        preflight_module.importlib,
        "import_module",
        lambda name: SimpleNamespace(
            get_available_providers=lambda: ["QNNExecutionProvider"],
            register_execution_provider_library=lambda ep, path: None,
            unregister_execution_provider_library=lambda ep: None,
            get_ep_devices=lambda: [SimpleNamespace(ep_name="QNNExecutionProvider")],
        )
        if name == "onnxruntime"
        else SimpleNamespace(
            __name__=name,
            get_library_path=lambda: "C:/qnn/onnxruntime_providers_qnn.dll",
            get_qnn_htp_path=lambda: "C:/qnn/QnnHtp.dll",
        )
        if name == "onnxruntime_qnn"
        else SimpleNamespace(__name__=name),
    )
    monkeypatch.setattr(preflight_module.importlib.metadata, "version", lambda name: "2.0.0")
    monkeypatch.setattr(Path, "exists", lambda self: True)

    result = preflight_module.run_preflight(
        _profile(os_name="windows", arch="arm64", npu_available=True, npu_vendor="qualcomm"),
        ["hw-cpu-base", "hw-arm64-base", "hw-npu-qualcomm-qnn"],
    )

    assert "import:onnxruntime-qnn" in result.tokens
    assert "qnn:plugin_library" in result.tokens
    assert "qnn:htp_path" in result.tokens
    assert "qnn:ep_device" in result.tokens


def test_preflight_emits_qnn_ep_missing_token_when_ep_not_registered(monkeypatch) -> None:
    preflight_module._CACHE.clear()
    monkeypatch.setattr(preflight_module, "_bootstrap_windows_dlls", lambda profile, tokens, log: None)

    def fake_import(name: str):
        if name == "onnxruntime":
            return SimpleNamespace(
                get_available_providers=lambda: ["CPUExecutionProvider"],
                register_execution_provider_library=lambda ep, path: None,
                unregister_execution_provider_library=lambda ep: None,
                get_ep_devices=lambda: [SimpleNamespace(ep_name="CPUExecutionProvider")],
            )
        if name == "onnxruntime_qnn":
            return SimpleNamespace(
                __name__=name,
                get_library_path=lambda: "C:/qnn/onnxruntime_providers_qnn.dll",
                get_qnn_htp_path=lambda: "C:/qnn/QnnHtp.dll",
            )
        return SimpleNamespace(__name__=name)

    monkeypatch.setattr(preflight_module.importlib, "import_module", fake_import)
    monkeypatch.setattr(preflight_module.importlib.metadata, "version", lambda name: "2.0.0")
    monkeypatch.setattr(Path, "exists", lambda self: True)

    result = preflight_module.run_preflight(
        _profile(os_name="windows", arch="arm64", npu_available=True, npu_vendor="qualcomm"),
        ["hw-cpu-base", "hw-arm64-base", "hw-npu-qualcomm-qnn"],
    )

    assert "ep:QNNExecutionProvider:MISSING" in result.tokens
    assert "qnn:ep_device:MISSING" in result.tokens


def test_preflight_emits_qnn_dll_token_when_qnnhtp_is_discoverable(monkeypatch) -> None:
    preflight_module._CACHE.clear()
    tmp_path = Path("C:/qnn-sdk")
    existing_paths = {
        tmp_path,
        tmp_path / "bin",
        tmp_path / "bin" / "QnnHtp.dll",
    }

    monkeypatch.setattr(
        Path,
        "exists",
        lambda self: self in existing_paths,
    )

    monkeypatch.setattr(preflight_module, "_available_dll_directory_api", lambda: None)
    monkeypatch.setattr(
        preflight_module,
        "_candidate_dll_roots",
        lambda profile: [("QnnHtp", tmp_path)],
    )
    monkeypatch.setattr(preflight_module.importlib, "import_module", lambda name: SimpleNamespace(__name__=name))
    monkeypatch.setattr(preflight_module.importlib.metadata, "version", lambda name: "2.0.0")

    result = preflight_module.run_preflight(
        _profile(os_name="windows", arch="arm64", npu_available=True, npu_vendor="qualcomm"),
        ["hw-npu-qualcomm-qnn"],
    )

    assert "dll:QnnHtp" in result.tokens


def test_stt_readiness_reports_qnn_defined_and_selects_cpu_with_deferred_qnn_reason() -> None:
    selected_device, ready, reason = derive_stt_device_readiness(
        _preflight("import:onnxruntime-qnn:MISSING", "ep:QNNExecutionProvider:MISSING", "dll:QnnHtp:MISSING"),
        _profile(os_name="windows", arch="arm64", npu_available=True, npu_vendor="qualcomm"),
    )

    assert (selected_device, ready) == ("cpu", True)
    assert reason == "selecting cpu"


def test_stt_readiness_selects_qnn_when_qnn_tokens_are_proven() -> None:
    selected_device, ready, reason = derive_stt_device_readiness(
        _preflight("import:onnxruntime-qnn", "ep:QNNExecutionProvider", "dll:QnnHtp"),
        _profile(os_name="windows", arch="arm64", npu_available=True, npu_vendor="qualcomm"),
    )

    assert (selected_device, ready) == ("qnn", True)
    assert reason == "qnn prerequisites proven; selecting qnn"
