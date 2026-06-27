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
