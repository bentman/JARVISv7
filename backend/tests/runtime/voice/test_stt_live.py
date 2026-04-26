from __future__ import annotations

import re
import wave
from pathlib import Path

import numpy as np
import pytest

from backend.app.runtimes.stt.onnx_whisper_runtime import OnnxWhisperRuntime
from backend.tests.conftest import SKIP_UNLESS_LIVE


FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "hello_world.wav"


def _normalize_transcript(transcript: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", transcript.lower()).split())


def _load_mono_pcm16_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
        sample_rate = wav_file.getframerate()
        frame_count = wav_file.getnframes()
        raw_audio = wav_file.readframes(frame_count)

    if channels != 1:
        raise ValueError(f"expected mono WAV fixture, got {channels} channels")
    if sample_width != 2:
        raise ValueError(f"expected 16-bit PCM WAV fixture, got {sample_width * 8}-bit samples")

    audio = np.frombuffer(raw_audio, dtype="<i2").astype(np.float32) / 32768.0
    return audio, sample_rate


@pytest.mark.live
@pytest.mark.stt
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_stt_cpu_transcribes_hello_world_fixture_on_current_host():
    runtime = OnnxWhisperRuntime(device="cpu")

    assert runtime.is_available()
    audio, sample_rate = _load_mono_pcm16_wav(FIXTURE_PATH)
    transcript = runtime.transcribe(audio, sample_rate)

    assert "hello world" in _normalize_transcript(transcript)