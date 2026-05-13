from __future__ import annotations

from pathlib import Path

import onnxruntime
import pytest

from backend.app.models.catalog import get_model_entry
from backend.tests.conftest import SKIP_UNLESS_DIRECTML, SKIP_UNLESS_LIVE


def _whisper_encoder_model_path() -> Path:
    entry = get_model_entry("stt", "whisper-small-onnx")
    return entry.path / "encoder_model.onnx"


@pytest.mark.live
@pytest.mark.directml
@pytest.mark.stt
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_DIRECTML, reason="requires DirectML execution provider readiness")
def test_directml_ep_registers_in_onnxruntime() -> None:
    providers = list(onnxruntime.get_available_providers())
    assert "DmlExecutionProvider" in providers


@pytest.mark.live
@pytest.mark.directml
@pytest.mark.stt
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_DIRECTML, reason="requires DirectML execution provider readiness")
def test_whisper_model_loads_with_directml_ep() -> None:
    model_path = _whisper_encoder_model_path()
    assert model_path.is_file(), f"missing Whisper encoder model at {model_path}"

    session = onnxruntime.InferenceSession(
        str(model_path),
        providers=["DmlExecutionProvider", "CPUExecutionProvider"],
    )
    providers = session.get_providers()
    assert "DmlExecutionProvider" in providers
