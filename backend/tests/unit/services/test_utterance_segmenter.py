from __future__ import annotations

import numpy as np
from backend.app.runtimes.vad import EnergyVADRuntime
from backend.app.services.audio_stream import AudioChunk
from backend.app.services.utterance_segmenter import UtteranceSegmenter


def _chunk(value: float, sequence: int, samples: int = 4) -> AudioChunk:
    return AudioChunk(
        samples=np.full(samples, value, dtype=np.float32),
        sample_rate=16000,
        sequence=sequence,
        captured_at=float(sequence),
    )


def test_segmenter_detects_speech_start_and_silence_end() -> None:
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.05),
        sample_rate=16000,
        pre_roll_s=0.00025,
        speech_start_s=0.0005,
        min_speech_s=0.0005,
        silence_end_s=0.0005,
        no_speech_timeout_s=1.0,
    )

    result = segmenter.capture([_chunk(0.0, 1), _chunk(0.2, 2), _chunk(0.2, 3), _chunk(0.0, 4), _chunk(0.0, 5)])

    assert result.speech_started is True
    assert result.reason == "silence"
    assert result.speech_chunks == 2
    assert np.array_equal(result.audio[:4], np.zeros(4, dtype=np.float32))
    assert result.audio.shape == (20,)


def test_segmenter_reports_no_speech_after_timeout() -> None:
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.05),
        sample_rate=16000,
        no_speech_timeout_s=0.0005,
    )

    result = segmenter.capture([_chunk(0.0, 1), _chunk(0.0, 2)])

    assert result.speech_started is False
    assert result.reason == "no-speech"
    assert result.audio.size == 0
    assert result.diagnostics.reason == "no-speech"
    assert result.diagnostics.chunks == 2
    assert result.diagnostics.sample_count == 8
    assert result.diagnostics.rms == 0.0


def test_segmenter_reports_too_short_when_stream_ends_before_minimum_duration() -> None:
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.05),
        sample_rate=16000,
        min_speech_s=0.001,
        speech_start_s=0.00025,
    )

    result = segmenter.capture([_chunk(0.2, 1)])

    assert result.speech_started is True
    assert result.reason == "too-short"
    assert result.audio.shape == (4,)


def test_segmenter_stops_at_max_duration() -> None:
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.05),
        sample_rate=16000,
        max_duration_s=0.00075,
        speech_start_s=0.00025,
        min_speech_s=0.0,
        silence_end_s=1.0,
    )

    result = segmenter.capture([_chunk(0.2, 1), _chunk(0.2, 2), _chunk(0.2, 3)])

    assert result.reason == "max-duration"
    assert result.audio.shape == (12,)
    assert result.diagnostics.duration_s == 12 / 16000
    assert result.diagnostics.max_chunk_rms > 0.19


def test_segmenter_includes_bounded_pre_roll_before_speech() -> None:
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.05),
        sample_rate=16000,
        pre_roll_s=0.0005,
        speech_start_s=0.00025,
        min_speech_s=0.00025,
        silence_end_s=0.00025,
    )

    result = segmenter.capture([_chunk(0.0, 1), _chunk(0.0, 2), _chunk(0.0, 3), _chunk(0.2, 4), _chunk(0.0, 5)])

    assert result.reason == "silence"
    assert result.audio.shape == (16,)
    assert np.array_equal(result.audio[:8], np.zeros(8, dtype=np.float32))
    assert np.array_equal(result.audio[8:12], np.full(4, 0.2, dtype=np.float32))


def test_segmenter_fixture_tolerates_operator_delay_with_resident_timeout() -> None:
    import wave
    from pathlib import Path

    fixture = Path("backend/tests/fixtures/hello_world.wav")
    with wave.open(str(fixture), "rb") as wav_file:
        sample_rate = wav_file.getframerate()
        audio = np.frombuffer(wav_file.readframes(wav_file.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    delayed = np.concatenate([np.zeros(int(2.5 * sample_rate), dtype=np.float32), audio])
    chunks = [
        AudioChunk(
            samples=delayed[index : index + 1280],
            sample_rate=sample_rate,
            sequence=index // 1280,
            captured_at=0.0,
        )
        for index in range(0, delayed.size, 1280)
    ]
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(),
        sample_rate=sample_rate,
        speech_start_s=0.08,
        no_speech_timeout_s=5.0,
        silence_end_s=0.5,
    )

    result = segmenter.capture(chunks)

    assert result.speech_started is True
    assert result.reason == "silence"
    assert result.diagnostics.speech_chunks > 0
    assert result.diagnostics.peak > 0.1


def test_segmenter_accepts_quiet_speech_above_calibrated_threshold() -> None:
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.02),
        sample_rate=16000,
        pre_roll_s=0.00025,
        speech_start_s=0.0005,
        min_speech_s=0.0005,
        silence_end_s=0.0005,
        noise_floor_multiplier=3.0,
        noise_floor_margin=0.002,
    )

    result = segmenter.capture([_chunk(0.004, 1), _chunk(0.025, 2), _chunk(0.025, 3), _chunk(0.0, 4), _chunk(0.0, 5)])

    assert result.speech_started is True
    assert result.reason == "silence"
    assert result.speech_chunks == 2
    assert result.diagnostics.noise_floor_rms < result.diagnostics.effective_speech_threshold


def test_segmenter_rejects_background_noise_below_adaptive_threshold() -> None:
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.015),
        sample_rate=16000,
        speech_start_s=0.0005,
        no_speech_timeout_s=0.001,
        noise_floor_multiplier=3.0,
        noise_floor_margin=0.003,
    )

    result = segmenter.capture([_chunk(0.012, 1), _chunk(0.018, 2), _chunk(0.018, 3), _chunk(0.018, 4)])

    assert result.speech_started is False
    assert result.reason == "no-speech"
    assert result.speech_chunks == 0
    assert result.diagnostics.effective_speech_threshold > 0.018


def test_segmenter_debounces_single_background_spike_before_speech_start() -> None:
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.05),
        sample_rate=16000,
        speech_start_s=0.0005,
        no_speech_timeout_s=0.001,
    )

    result = segmenter.capture([_chunk(0.0, 1), _chunk(0.2, 2), _chunk(0.0, 3), _chunk(0.0, 4)])

    assert result.speech_started is False
    assert result.reason == "no-speech"
    assert result.speech_chunks == 0


def test_segmenter_keeps_brief_hesitation_inside_utterance() -> None:
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.05),
        sample_rate=16000,
        speech_start_s=0.0005,
        min_speech_s=0.0005,
        silence_end_s=0.00075,
    )

    result = segmenter.capture(
        [
            _chunk(0.2, 1),
            _chunk(0.2, 2),
            _chunk(0.0, 3),
            _chunk(0.2, 4),
            _chunk(0.2, 5),
            _chunk(0.0, 6),
            _chunk(0.0, 7),
            _chunk(0.0, 8),
        ]
    )

    assert result.speech_started is True
    assert result.reason == "silence"
    assert result.speech_chunks == 4
    assert result.audio.shape == (32,)


def test_segmenter_reports_stream_ended_after_confirmed_speech_without_endpoint() -> None:
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.05),
        sample_rate=16000,
        speech_start_s=0.0005,
        min_speech_s=0.0005,
        silence_end_s=1.0,
    )

    result = segmenter.capture([_chunk(0.2, 1), _chunk(0.2, 2)])

    assert result.speech_started is True
    assert result.reason == "stream-ended"
    assert result.speech_chunks == 2
