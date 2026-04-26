from __future__ import annotations

import re
from pathlib import Path

import pytest
import soundfile as sf

from backend.app.runtimes.stt.onnx_whisper_runtime import OnnxWhisperRuntime
from backend.tests.conftest import SKIP_UNLESS_LIVE


FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "hello_world.wav"


def _normalize_transcript(transcript: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", transcript.lower()).split())


@pytest.mark.live
@pytest.mark.stt
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_stt_cpu_transcribes_hello_world_fixture_on_current_host():
    runtime = OnnxWhisperRuntime(device="cpu")

    assert runtime.is_available()
    audio, sample_rate = sf.read(FIXTURE_PATH, dtype="float32")
    transcript = runtime.transcribe(audio, sample_rate)

    assert "hello world" in _normalize_transcript(transcript)