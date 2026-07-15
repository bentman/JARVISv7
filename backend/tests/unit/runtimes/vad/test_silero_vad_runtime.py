from __future__ import annotations

import wave
from pathlib import Path

import numpy as np
import pytest
from backend.app.core.settings import Settings
from backend.app.runtimes.vad.energy_runtime import EnergyVADRuntime
from backend.app.runtimes.vad.silero_runtime import (
    SILERO_CONTEXT_SAMPLES,
    SILERO_MODEL_URL,
    SILERO_WINDOW_SAMPLES,
    SileroVADRuntime,
)
from backend.app.runtimes.vad.vad_runtime import select_vad_runtime

FIXTURE_DIR = Path(__file__).resolve().parents[3] / "fixtures"


class FakeSession:
    def __init__(self, probabilities: list[float]) -> None:
        self._probabilities = list(probabilities)
        self.calls: list[dict[str, np.ndarray]] = []

    def run(self, output_names, feeds):
        assert output_names is None
        self.calls.append({name: np.array(value, copy=True) for name, value in feeds.items()})
        probability = self._probabilities.pop(0)
        state = feeds["state"] + 1.0
        return [np.array([[probability]], dtype=np.float32), state]


def _fake_runtime(probabilities: list[float], **kwargs) -> tuple[SileroVADRuntime, FakeSession]:
    runtime = SileroVADRuntime(model_path=Path("unused/silero_vad.onnx"), **kwargs)
    session = FakeSession(probabilities)
    runtime._session = session
    return runtime, session


def test_silero_buffers_1280_sample_chunk_into_512_sample_windows() -> None:
    runtime, session = _fake_runtime([0.9, 0.9])
    chunk = np.linspace(-0.5, 0.5, 1280, dtype=np.float32)

    decision = runtime.detect(chunk, 16000)

    assert len(session.calls) == 2
    for call in session.calls:
        assert call["input"].shape == (1, SILERO_CONTEXT_SAMPLES + SILERO_WINDOW_SAMPLES)
        assert call["input"].dtype == np.float32
        assert call["sr"] == 16000
    assert runtime._buffer.size == 1280 - 2 * SILERO_WINDOW_SAMPLES
    assert decision.speech is True
    assert decision.probability == pytest.approx(0.9)
    assert decision.rms > 0.0


def test_silero_threads_state_between_windows() -> None:
    runtime, session = _fake_runtime([0.9, 0.9])

    runtime.detect(np.ones(1280, dtype=np.float32), 16000)

    assert np.all(session.calls[0]["state"] == 0.0)
    assert session.calls[0]["state"].shape == (2, 1, 128)
    assert np.all(session.calls[1]["state"] == 1.0)
    assert np.all(runtime._state == 2.0)


def test_silero_prepends_previous_window_context() -> None:
    runtime, session = _fake_runtime([0.9, 0.9])
    chunk = np.arange(1280, dtype=np.float32) / 1280.0

    runtime.detect(chunk, 16000)

    first, second = session.calls
    assert np.all(first["input"][0, :SILERO_CONTEXT_SAMPLES] == 0.0)
    np.testing.assert_array_equal(first["input"][0, SILERO_CONTEXT_SAMPLES:], chunk[:512])
    np.testing.assert_array_equal(second["input"][0, :SILERO_CONTEXT_SAMPLES], chunk[448:512])
    np.testing.assert_array_equal(second["input"][0, SILERO_CONTEXT_SAMPLES:], chunk[512:1024])


def test_silero_hysteresis_holds_speech_between_thresholds_and_releases_below_neg() -> None:
    runtime, _session = _fake_runtime([0.6, 0.4, 0.3], threshold=0.5, neg_threshold=0.35)
    window = np.ones(SILERO_WINDOW_SAMPLES, dtype=np.float32)

    onset = runtime.detect(window, 16000)
    held = runtime.detect(window, 16000)
    released = runtime.detect(window, 16000)

    assert onset.speech is True
    assert held.speech is True
    assert held.probability == pytest.approx(0.4)
    assert released.speech is False
    assert released.probability == pytest.approx(0.3)


def test_silero_reset_clears_buffer_state_context_and_hysteresis() -> None:
    runtime, session = _fake_runtime([0.9, 0.9])
    runtime.detect(np.ones(SILERO_WINDOW_SAMPLES, dtype=np.float32), 16000)
    runtime.detect(np.ones(256, dtype=np.float32), 16000)  # partial window buffered

    runtime.reset()

    decision = runtime.detect(np.full(SILERO_WINDOW_SAMPLES, 0.25, dtype=np.float32), 16000)

    assert len(session.calls) == 2  # buffered partial window was discarded by reset
    fresh_call = session.calls[-1]
    assert np.all(fresh_call["state"] == 0.0)
    assert np.all(fresh_call["input"][0, :SILERO_CONTEXT_SAMPLES] == 0.0)
    assert decision.speech is True


def test_silero_no_new_window_keeps_previous_decision() -> None:
    runtime, session = _fake_runtime([0.9])

    first = runtime.detect(np.ones(SILERO_WINDOW_SAMPLES, dtype=np.float32), 16000)
    partial = runtime.detect(np.ones(128, dtype=np.float32), 16000)

    assert first.speech is True
    assert partial.speech is True
    assert partial.probability == pytest.approx(0.9)
    assert len(session.calls) == 1


def test_silero_empty_chunk_reports_no_speech_without_session() -> None:
    runtime = SileroVADRuntime(model_path=Path("missing/silero_vad.onnx"))

    decision = runtime.detect(np.array([], dtype=np.float32), 16000)

    assert decision.speech is False
    assert decision.probability == 0.0
    assert decision.rms == 0.0


def test_silero_rejects_unsupported_sample_rate() -> None:
    runtime, _session = _fake_runtime([0.9])

    with pytest.raises(ValueError, match="16000"):
        runtime.detect(np.ones(512, dtype=np.float32), 8000)


def test_silero_is_available_false_when_model_missing(tmp_path: Path) -> None:
    runtime = SileroVADRuntime(model_path=tmp_path / "silero_vad.onnx")

    assert runtime.is_available() is False
    reason = runtime.unavailable_reason()
    assert reason is not None
    assert SILERO_MODEL_URL in reason
    with pytest.raises(RuntimeError, match="silero VAD model missing"):
        runtime.detect(np.ones(512, dtype=np.float32), 16000)


def _settings(mode: str) -> Settings:
    settings = Settings()
    settings.resident_voice_vad = mode
    settings.resident_voice_speech_rms_threshold = 0.02
    return settings


def test_select_vad_auto_falls_back_to_energy_when_model_missing(tmp_path: Path) -> None:
    runtime, reason = select_vad_runtime(_settings("auto"), model_path=tmp_path / "silero_vad.onnx")

    assert isinstance(runtime, EnergyVADRuntime)
    assert runtime.speech_rms_threshold == 0.02
    assert "fallback" in reason
    assert "silero VAD model missing" in reason


def test_select_vad_explicit_silero_reports_degraded_reason(tmp_path: Path) -> None:
    runtime, reason = select_vad_runtime(_settings("silero"), model_path=tmp_path / "silero_vad.onnx")

    assert isinstance(runtime, EnergyVADRuntime)
    assert "degraded" in reason
    assert "silero VAD model missing" in reason


def test_select_vad_explicit_energy_always_selects_energy(tmp_path: Path) -> None:
    model_path = tmp_path / "silero_vad.onnx"
    model_path.write_bytes(b"onnx")

    runtime, reason = select_vad_runtime(_settings("energy"), model_path=model_path)

    assert isinstance(runtime, EnergyVADRuntime)
    assert "RESIDENT_VOICE_VAD=energy" in reason


def test_select_vad_auto_prefers_silero_when_model_present(tmp_path: Path) -> None:
    model_path = tmp_path / "silero_vad.onnx"
    model_path.write_bytes(b"onnx")

    runtime, reason = select_vad_runtime(_settings("auto"), model_path=model_path)

    assert isinstance(runtime, SileroVADRuntime)
    assert str(model_path) in reason


def _load_wav_float32(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as wav_file:
        assert wav_file.getnchannels() == 1
        assert wav_file.getframerate() == 16000
        assert wav_file.getsampwidth() == 2
        samples = np.frombuffer(wav_file.readframes(wav_file.getnframes()), dtype="<i2")
    return samples.astype(np.float32) / 32768.0


def _max_probability(runtime: SileroVADRuntime, audio: np.ndarray) -> float:
    max_probability = 0.0
    for start in range(0, audio.size - 1280 + 1, 1280):
        decision = runtime.detect(audio[start : start + 1280], 16000)
        max_probability = max(max_probability, decision.probability)
    return max_probability


def test_silero_real_model_separates_speech_from_silence_and_noise() -> None:
    runtime = SileroVADRuntime()
    if not runtime.is_available():
        pytest.skip(f"silero VAD model unavailable at {runtime.model_path}")

    speech_probability = _max_probability(runtime, _load_wav_float32(FIXTURE_DIR / "hey_jarvis_ref.wav"))

    runtime.reset()
    silence_probability = _max_probability(runtime, np.zeros(16000, dtype=np.float32))

    runtime.reset()
    rng = np.random.default_rng(7)
    noise = (rng.standard_normal(16000) * 0.05).astype(np.float32)
    noise_probability = _max_probability(runtime, noise)

    assert speech_probability >= runtime.threshold
    assert silence_probability < runtime.neg_threshold
    assert noise_probability < runtime.threshold
