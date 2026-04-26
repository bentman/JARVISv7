from __future__ import annotations

import numpy as np
import pytest

from backend.app.runtimes.tts.kokoro_onnx_runtime import KOKORO_SAMPLE_RATE, KokoroOnnxRuntime
from backend.tests.conftest import SKIP_UNLESS_LIVE


@pytest.mark.live
@pytest.mark.tts
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_tts_cpu_synthesizes_known_text_returns_nonempty_array():
    runtime = KokoroOnnxRuntime(device="cpu")

    assert runtime.is_available()
    audio = runtime.synthesize("hello world")

    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.size > 0
    assert runtime.sample_rate() == KOKORO_SAMPLE_RATE