from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.app.hardware import qnn_provider


def test_resolve_qnn_htp_backend_path_uses_onnxruntime_qnn_package(monkeypatch, tmp_path) -> None:
    ort_root = tmp_path / "onnxruntime"
    qnn_root = tmp_path / "onnxruntime_qnn"
    ort_root.mkdir()
    qnn_root.mkdir()
    ort_file = ort_root / "__init__.py"
    qnn_file = qnn_root / "__init__.py"
    htp_path = qnn_root / "QnnHtp.dll"
    ort_file.write_text("", encoding="utf-8")
    qnn_file.write_text("", encoding="utf-8")
    htp_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(qnn_provider.onnxruntime, "__file__", str(ort_file), raising=False)
    monkeypatch.setattr(
        qnn_provider,
        "_optional_onnxruntime_qnn_module",
        lambda: SimpleNamespace(__file__=str(qnn_file)),
    )
    monkeypatch.setattr(qnn_provider.os, "getenv", lambda name: None)

    assert qnn_provider.resolve_qnn_htp_backend_path() == htp_path


def test_activate_qnn_execution_provider_registers_packaged_provider(monkeypatch, tmp_path) -> None:
    qnn_provider._ACTIVATION_RESULT = None
    qnn_provider._DLL_DIRECTORY_HANDLES.clear()
    qnn_root = tmp_path / "onnxruntime_qnn"
    qnn_root.mkdir()
    library_path = qnn_root / "onnxruntime_providers_qnn.dll"
    htp_path = qnn_root / "QnnHtp.dll"
    library_path.write_text("", encoding="utf-8")
    htp_path.write_text("", encoding="utf-8")
    providers = ["AzureExecutionProvider", "CPUExecutionProvider"]
    registered: list[tuple[str, str]] = []
    added_dll_dirs: list[str] = []

    monkeypatch.setattr(qnn_provider, "_available_providers", lambda: list(providers))
    monkeypatch.setattr(
        qnn_provider,
        "_optional_onnxruntime_qnn_module",
        lambda: SimpleNamespace(
            LIB_DIR_FULL_PATH=str(qnn_root),
            get_library_path=lambda: str(library_path),
            get_qnn_htp_path=lambda: str(htp_path),
        ),
    )
    monkeypatch.setattr(
        qnn_provider.os,
        "add_dll_directory",
        lambda path: added_dll_dirs.append(path) or SimpleNamespace(close=lambda: None),
        raising=False,
    )

    def fake_register(name: str, path: str) -> None:
        registered.append((name, path))
        providers.append("QNNExecutionProvider")

    monkeypatch.setattr(
        qnn_provider.onnxruntime,
        "register_execution_provider_library",
        fake_register,
        raising=False,
    )

    result = qnn_provider.activate_qnn_execution_provider()

    assert result.provider_registered is True
    assert result.provider_library_path == library_path
    assert result.dll_directory_path == qnn_root
    assert result.error is None
    assert added_dll_dirs == [str(qnn_root)]
    assert registered == [("QNNExecutionProvider", str(library_path))]


def test_activate_qnn_execution_provider_fails_closed_when_library_missing(monkeypatch, tmp_path) -> None:
    qnn_provider._ACTIVATION_RESULT = None
    qnn_root = tmp_path / "onnxruntime_qnn"
    qnn_root.mkdir()

    monkeypatch.setattr(qnn_provider, "_available_providers", lambda: ["CPUExecutionProvider"])
    monkeypatch.setattr(
        qnn_provider,
        "_optional_onnxruntime_qnn_module",
        lambda: SimpleNamespace(LIB_DIR_FULL_PATH=str(qnn_root)),
    )

    result = qnn_provider.activate_qnn_execution_provider()

    assert result.provider_registered is False
    assert result.error == "onnxruntime_qnn provider library not found"


def test_qnn_session_failure_classifies_epcontext_not_claimed() -> None:
    reason = qnn_provider._classify_qnn_session_failure(
        RuntimeError(
            "This session contains graph nodes that are assigned to the default CPU EP, "
            "but fallback to CPU EP has been explicitly disabled by the user."
        )
    )

    assert reason == "qnn-epcontext-not-claimed"


def test_qnn_session_failure_classifies_cpu_epcontext_kernel_error() -> None:
    reason = qnn_provider._classify_qnn_session_failure(
        RuntimeError(
            "Failed to find kernel for com.microsoft.EPContext(1) "
            "(node:'QNNContext' ep:'CPUExecutionProvider'). Kernel not found"
        )
    )

    assert reason == "qnn-epcontext-not-claimed"


def test_create_qnn_session_prefers_ep_device_initialization(monkeypatch, tmp_path) -> None:
    model_path = tmp_path / "model.onnx"
    model_path.write_text("x", encoding="utf-8")
    qnn_device = SimpleNamespace(ep_name="QNNExecutionProvider")
    calls: list[tuple[str, object]] = []

    class FakeSessionOptions:
        def add_session_config_entry(self, key: str, value: str) -> None:
            calls.append(("config", (key, value)))

        def add_provider_for_devices(self, devices: list[object], provider_options: dict[str, str]) -> None:
            calls.append(("ep_devices", (devices, provider_options)))

    class FakeSession:
        def get_providers(self) -> list[str]:
            return ["QNNExecutionProvider", "CPUExecutionProvider"]

    monkeypatch.setattr(
        qnn_provider,
        "activate_qnn_execution_provider",
        lambda: qnn_provider.QnnProviderActivationResult(provider_registered=True),
    )
    monkeypatch.setattr(qnn_provider, "get_qnn_provider_options", lambda: {"backend_path": "QnnHtp.dll"})
    monkeypatch.setattr(qnn_provider.onnxruntime, "get_ep_devices", lambda: [qnn_device], raising=False)
    monkeypatch.setattr(qnn_provider.onnxruntime, "SessionOptions", FakeSessionOptions)
    monkeypatch.setattr(
        qnn_provider.onnxruntime,
        "InferenceSession",
        lambda path, sess_options: FakeSession(),
    )

    session, method = qnn_provider.create_qnn_session(model_path)

    assert method == "ep_device_with_backend_path"
    assert session.get_providers()[0] == "QNNExecutionProvider"
    assert calls == [
        ("config", ("session.disable_cpu_ep_fallback", "1")),
        ("ep_devices", ([qnn_device], {"backend_path": "QnnHtp.dll"})),
    ]
