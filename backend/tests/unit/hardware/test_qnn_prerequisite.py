from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware import preflight as preflight_module


def _profile(**overrides) -> HardwareProfile:
    return HardwareProfile(**overrides)


def test_qnn_dll_token_present_when_path_configured(monkeypatch) -> None:
    preflight_module._CACHE.clear()
    qnn_root = Path("C:/qnn-sdk")
    existing_paths = {
        qnn_root,
        qnn_root / "bin",
        qnn_root / "bin" / "QnnHtp.dll",
    }

    monkeypatch.setattr(Path, "exists", lambda self: self in existing_paths)
    monkeypatch.setattr(preflight_module, "_available_dll_directory_api", lambda: None)
    monkeypatch.setattr(preflight_module, "_candidate_dll_roots", lambda profile: [("QnnHtp", qnn_root)])
    monkeypatch.setattr(preflight_module.importlib, "import_module", lambda name: SimpleNamespace(__name__=name))
    monkeypatch.setattr(preflight_module.importlib.metadata, "version", lambda name: "2.0.0")

    result = preflight_module.run_preflight(
        _profile(os_name="windows", arch="arm64", npu_available=True, npu_vendor="qualcomm"),
        ["hw-npu-qualcomm-qnn"],
    )

    assert "dll:QnnHtp" in result.tokens


def test_qnn_ep_token_present_when_ep_available(monkeypatch) -> None:
    preflight_module._CACHE.clear()
    monkeypatch.setattr(preflight_module, "_bootstrap_windows_dlls", lambda profile, tokens, log: None)

    def fake_import(name: str):
        if name == "onnxruntime":
            return SimpleNamespace(
                get_available_providers=lambda: ["QNNExecutionProvider", "CPUExecutionProvider"],
                register_execution_provider_library=lambda ep, path: None,
                unregister_execution_provider_library=lambda ep: None,
                get_ep_devices=lambda: [SimpleNamespace(ep_name="QNNExecutionProvider")],
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

    assert "ep:QNNExecutionProvider" in result.tokens


def test_qnn_ep_token_missing_when_ep_absent(monkeypatch) -> None:
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
