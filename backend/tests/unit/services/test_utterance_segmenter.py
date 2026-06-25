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


def test_segmenter_reports_too_short_when_stream_ends_before_minimum_duration() -> None:
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.05),
        sample_rate=16000,
        min_speech_s=0.001,
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
        min_speech_s=0.0,
        silence_end_s=1.0,
    )

    result = segmenter.capture([_chunk(0.2, 1), _chunk(0.2, 2), _chunk(0.2, 3)])

    assert result.reason == "max-duration"
    assert result.audio.shape == (12,)


def test_segmenter_includes_bounded_pre_roll_before_speech() -> None:
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.05),
        sample_rate=16000,
        pre_roll_s=0.0005,
        min_speech_s=0.00025,
        silence_end_s=0.00025,
    )

    result = segmenter.capture([_chunk(0.0, 1), _chunk(0.0, 2), _chunk(0.0, 3), _chunk(0.2, 4), _chunk(0.0, 5)])

    assert result.reason == "silence"
    assert result.audio.shape == (16,)
    assert np.array_equal(result.audio[:8], np.zeros(8, dtype=np.float32))
    assert np.array_equal(result.audio[8:12], np.full(4, 0.2, dtype=np.float32))
