from __future__ import annotations

from pathlib import Path

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
def test_qnn_encoder_decoder_session_init_with_cpu_fallback_disabled() -> None:
    entry = get_model_entry("stt", "whisper-tiny-qnn-precompiled-snapdragon-x-elite")
    model_root = entry.local_path

    encoder_path = _find_required_model_file(model_root, "encoder_model.onnx")
    decoder_path = _find_required_model_file(model_root, "decoder_model_merged.onnx")

    encoder_session, encoder_method = create_qnn_session(encoder_path, disable_cpu_fallback=True)
    decoder_session, decoder_method = create_qnn_session(decoder_path, disable_cpu_fallback=True)

    assert encoder_session.get_providers() == ["QNNExecutionProvider"]
    assert decoder_session.get_providers() == ["QNNExecutionProvider"]
