from __future__ import annotations

from pathlib import Path

import onnxruntime
import pytest

from backend.app.hardware.qnn_provider import create_qnn_session
from backend.app.models.catalog import get_model_entry
from backend.tests.conftest import SKIP_UNLESS_ARM64, SKIP_UNLESS_LIVE, SKIP_UNLESS_QNN


def _find_required_model_file(root: Path, filename: str) -> Path:
    candidates = sorted(path for path in root.rglob(filename) if path.is_file())
    if not candidates:
        raise FileNotFoundError(f"missing required model file '{filename}' under {root}")
    return candidates[0]


@pytest.mark.live
@pytest.mark.arm64
@pytest.mark.qnn
@pytest.mark.stt
@pytest.mark.requires_qairt
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_ARM64, reason="requires ARM64 host")
@pytest.mark.skipif(SKIP_UNLESS_QNN, reason="requires QNN execution provider readiness")
def test_qnn_dll_discoverable_via_qairt_sdk_path() -> None:
    import onnxruntime_qnn

    backend_path = Path(onnxruntime_qnn.get_library_path())
    htp_path = Path(onnxruntime_qnn.get_qnn_htp_path())

    assert backend_path.is_file(), f"QNN plugin library not found at {backend_path}"
    assert htp_path.is_file(), f"QNN HTP backend not found at {htp_path}"


@pytest.mark.live
@pytest.mark.arm64
@pytest.mark.qnn
@pytest.mark.stt
@pytest.mark.requires_qairt
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_ARM64, reason="requires ARM64 host")
@pytest.mark.skipif(SKIP_UNLESS_QNN, reason="requires QNN execution provider readiness")
def test_qnn_ep_registers_in_onnxruntime() -> None:
    import onnxruntime_qnn

    backend_path = str(onnxruntime_qnn.get_library_path())
    onnxruntime.register_execution_provider_library("QNNExecutionProvider", backend_path)
    try:
        ep_devices = list(onnxruntime.get_ep_devices())
        assert any(device.ep_name == "QNNExecutionProvider" for device in ep_devices)
    finally:
        try:
            onnxruntime.unregister_execution_provider_library("QNNExecutionProvider")
        except Exception:
            pass


@pytest.mark.live
@pytest.mark.arm64
@pytest.mark.qnn
@pytest.mark.stt
@pytest.mark.requires_qairt
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_ARM64, reason="requires ARM64 host")
@pytest.mark.skipif(SKIP_UNLESS_QNN, reason="requires QNN execution provider readiness")
def test_qnn_compatible_whisper_artifact_loads_with_qnn_ep() -> None:
    import onnxruntime_qnn

    entry = get_model_entry("stt", "whisper-tiny-qnn-precompiled-snapdragon-x-elite")
    model_root = entry.local_path

    encoder_path = _find_required_model_file(model_root, "encoder.onnx")
    decoder_path = _find_required_model_file(model_root, "decoder.onnx")

    backend_path = str(onnxruntime_qnn.get_library_path())
    onnxruntime.register_execution_provider_library("QNNExecutionProvider", backend_path)
    try:
        ep_devices = list(onnxruntime.get_ep_devices())
        qnn_devices = [d for d in ep_devices if getattr(d, "ep_name", None) == "QNNExecutionProvider"]
        assert qnn_devices, "QNNExecutionProvider device list is empty"

        so_encoder = onnxruntime.SessionOptions()
        so_encoder.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        so_encoder.add_provider_for_devices(qnn_devices, {"backend_path": backend_path})
        encoder_session = onnxruntime.InferenceSession(str(encoder_path), sess_options=so_encoder)

        so_decoder = onnxruntime.SessionOptions()
        so_decoder.add_session_config_entry("session.disable_cpu_ep_fallback", "1")
        so_decoder.add_provider_for_devices(qnn_devices, {"backend_path": backend_path})
        decoder_session = onnxruntime.InferenceSession(str(decoder_path), sess_options=so_decoder)

        assert encoder_session.get_providers() == ["QNNExecutionProvider"]
        assert decoder_session.get_providers() == ["QNNExecutionProvider"]
    finally:
        try:
            onnxruntime.unregister_execution_provider_library("QNNExecutionProvider")
        except Exception:
            pass
