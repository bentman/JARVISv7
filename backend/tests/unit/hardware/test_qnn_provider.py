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
