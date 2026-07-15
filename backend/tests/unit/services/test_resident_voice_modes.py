from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
import pytest
from backend.app.conversation.engine import TurnResult
from backend.app.conversation.states import ConversationState
from backend.app.runtimes.vad import EnergyVADRuntime
from backend.app.services.audio_stream import ResidentAudioStream
from backend.app.services.resident_voice_invocation import ResidentVoiceInvocationService
from backend.app.services.utterance_segmenter import UtteranceSegmenter
from backend.tests.unit.services.test_session_service import _service as _session_service


class _FakeEngine:
    def __init__(self, calls: list[tuple[np.ndarray, int]]) -> None:
        self.calls = calls

    def run_voice_turn(self, audio: np.ndarray, sample_rate: int) -> TurnResult:
        self.calls.append((audio, sample_rate))
        return TurnResult(
            turn_id=f"turn-{len(self.calls)}",
            session_id="session-resident",
            transcript=f"transcript-{len(self.calls)}",
            response_text=f"response-{len(self.calls)}",
            final_state=ConversationState.IDLE,
        )


def _bare_service() -> ResidentVoiceInvocationService:
    return ResidentVoiceInvocationService(
        session_service=object(),  # type: ignore[arg-type]
        engine_provider=lambda: object(),  # type: ignore[return-value]
    )


def _blocking_source(stop_event: threading.Event):
    while not stop_event.is_set():
        time.sleep(0.01)
        if False:
            yield np.array([], dtype=np.float32)


def _segmenter() -> UtteranceSegmenter:
    return UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.05),
        sample_rate=16000,
        pre_roll_s=0.00025,
        speech_start_s=0.0005,
        min_speech_s=0.0005,
        silence_end_s=0.0005,
        no_speech_timeout_s=0.0005,
    )


def _wait_for(predicate, timeout_s: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached")


def _resident(calls: list[tuple[np.ndarray, int]], tmp_path: Path) -> tuple[ResidentVoiceInvocationService, ResidentAudioStream]:
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4, chunk_source_factory=_blocking_source)
    service = _session_service(tmp_path)
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: _FakeEngine(calls),  # type: ignore[return-value]
        audio_capture=lambda: (_ for _ in ()).throw(AssertionError("fallback capture should not run")),
        resident_stream=stream,
        utterance_segmenter=_segmenter(),
    )
    return resident, stream


def test_resident_voice_mode_defaults_to_ptt_only() -> None:
    service = _bare_service()

    assert service.mode() == "ptt-only"
    assert service.follow_up_status().continuous_active is False


def test_resident_voice_mode_changes_are_explicit_and_idempotent() -> None:
    service = _bare_service()

    assert service.set_mode("ptt-only") == "ptt-only"
    assert service.set_mode("ptt-only") == "ptt-only"
    assert service.mode() == "ptt-only"
    assert service.set_mode("hands-free") == "hands-free"
    assert service.set_mode("continuous") == "continuous"
    assert service.follow_up_status().continuous_active is True
    assert service.set_mode("ptt+wake") == "ptt+wake"
    assert service.follow_up_status().continuous_active is False


def test_resident_voice_mode_rejects_unknown_values() -> None:
    service = _bare_service()

    with pytest.raises(ValueError, match="unsupported resident voice mode"):
        service.set_mode("ambient")


def test_hands_free_listens_for_one_bounded_follow_up_after_successful_turn(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    resident, stream = _resident(calls, tmp_path)
    resident.set_mode("hands-free")
    stream.start()
    try:
        resident.enqueue("ptt", np.ones(8, dtype=np.float32), 16000)
        _wait_for(lambda: len(calls) == 1)
        _wait_for(lambda: resident.follow_up_status().listening)
        stream.publish_for_test(np.zeros(4, dtype=np.float32))
        stream.publish_for_test(np.full(4, 0.2, dtype=np.float32))
        stream.publish_for_test(np.full(4, 0.2, dtype=np.float32))
        stream.publish_for_test(np.zeros(4, dtype=np.float32))
        stream.publish_for_test(np.zeros(4, dtype=np.float32))
        _wait_for(lambda: len(calls) == 2)
    finally:
        stream.stop()

    assert calls[1][1] == 16000
    assert calls[1][0].shape == (12,)
    assert resident.status().invocation_source == "hands_free"
    assert resident.follow_up_status().listening is False


def test_hands_free_silence_timeout_does_not_enqueue_empty_follow_up(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    resident, stream = _resident(calls, tmp_path)
    resident.set_mode("hands-free")
    stream.start()
    try:
        resident.enqueue("ptt", np.ones(8, dtype=np.float32), 16000)
        _wait_for(lambda: len(calls) == 1)
        _wait_for(lambda: resident.follow_up_status().listening)
        stream.publish_for_test(np.zeros(4, dtype=np.float32))
        stream.publish_for_test(np.zeros(4, dtype=np.float32))
        _wait_for(lambda: not resident.follow_up_status().listening)
    finally:
        stream.stop()

    assert len(calls) == 1
    assert resident.status().invocation_source == "ptt"


def test_continuous_mode_requires_explicit_opt_in_and_reports_active_state(tmp_path: Path) -> None:
    calls: list[tuple[np.ndarray, int]] = []
    resident, stream = _resident(calls, tmp_path)

    assert resident.follow_up_status().continuous_active is False
    resident.set_mode("continuous")
    assert resident.follow_up_status().continuous_active is True

    stream.start()
    try:
        resident.enqueue("ptt", np.ones(8, dtype=np.float32), 16000)
        _wait_for(lambda: len(calls) == 1)
        _wait_for(lambda: resident.follow_up_status().source == "continuous")
        stream.publish_for_test(np.zeros(4, dtype=np.float32))
        stream.publish_for_test(np.full(4, 0.2, dtype=np.float32))
        stream.publish_for_test(np.full(4, 0.2, dtype=np.float32))
        stream.publish_for_test(np.zeros(4, dtype=np.float32))
        stream.publish_for_test(np.zeros(4, dtype=np.float32))
        _wait_for(lambda: len(calls) == 2)
        _wait_for(lambda: resident.follow_up_status().source == "continuous")
        stream.publish_for_test(np.zeros(4, dtype=np.float32))
        stream.publish_for_test(np.zeros(4, dtype=np.float32))
        _wait_for(lambda: not resident.follow_up_status().listening)
    finally:
        stream.stop()

    assert len(calls) == 2
    assert resident.status().invocation_source == "continuous"
    assert resident.follow_up_status().continuous_active is True
