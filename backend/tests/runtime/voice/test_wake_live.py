from __future__ import annotations

from pathlib import Path
import wave

import numpy as np
import pytest

from backend.app.runtimes.wake.openwakeword_runtime import OpenWakeWordRuntime
from backend.tests.conftest import SKIP_UNLESS_LIVE


FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "hey_jarvis.wav"


def _load_pcm_fixture(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 16000
        assert wav.getsampwidth() == 2
        raw = wav.readframes(wav.getnframes())
    return np.frombuffer(raw, dtype=np.int16)


@pytest.mark.live
@pytest.mark.wake
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_wake_openwakeword_detects_hey_jarvis_in_fixture_audio():
    runtime = OpenWakeWordRuntime(device="cpu")
    audio = _load_pcm_fixture(FIXTURE_PATH)

    assert runtime.is_available()
    detected = runtime.detect(audio)

    assert detected, f"expected wake detection score >= {runtime.threshold}, got {runtime.last_score}"