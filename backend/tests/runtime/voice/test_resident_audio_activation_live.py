from __future__ import annotations

import time

import numpy as np
import pytest
from backend.app.conversation.engine import TurnResult
from backend.app.conversation.states import ConversationState
from backend.app.runtimes.vad import EnergyVADRuntime
from backend.app.services.audio_stream import ResidentAudioStream
from backend.app.services.resident_voice_invocation import ResidentVoiceInvocationService
from backend.app.services.utterance_segmenter import UtteranceSegmenter
from backend.tests.conftest import SKIP_UNLESS_LIVE
from backend.tests.unit.services.test_session_service import _service


class _CaptureProbeEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[np.ndarray, int]] = []

    def run_voice_turn(self, audio: np.ndarray, sample_rate: int) -> TurnResult:
        self.calls.append((audio, sample_rate))
        return TurnResult(
            turn_id="resident-live-ptt",
            session_id="resident-live",
            transcript="resident live ptt",
            response_text="resident live ptt captured",
            final_state=ConversationState.IDLE,
        )


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_resident_ptt_uses_active_shared_stream_for_operator_utterance(tmp_path, capsys) -> None:
    service = _service(tmp_path)
    engine = _CaptureProbeEngine()
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=1280)
    segmenter = UtteranceSegmenter(
        vad=EnergyVADRuntime(speech_rms_threshold=0.02),
        sample_rate=16000,
        pre_roll_s=0.25,
        min_speech_s=0.2,
        silence_end_s=0.5,
        no_speech_timeout_s=5.0,
        max_duration_s=8.0,
    )
    resident = ResidentVoiceInvocationService(
        session_service=service,
        engine_provider=lambda: engine,  # type: ignore[return-value]
        audio_capture=lambda: (_ for _ in ()).throw(AssertionError("blocking fallback capture should not run")),
        resident_stream=stream,
        utterance_segmenter=segmenter,
    )

    stream.start()
    try:
        _operator_prompt(
            capsys,
            "PTT shared-stream validation",
            [
                "Capture starts after the countdown.",
                "Say a short phrase clearly, for example: 'resident PTT validation'.",
            ],
        )
        resident.ptt()
        _wait_for(lambda: service.status().last_transcript == "resident live ptt", timeout_s=10.0)
    finally:
        stream.stop()

    assert len(engine.calls) == 1
    audio, sample_rate = engine.calls[0]
    assert sample_rate == 16000
    assert audio.size > 0


def _operator_prompt(capsys, title: str, lines: list[str]) -> None:
    with capsys.disabled():
        print(f"\n[operator] {title}", flush=True)
        for line in lines:
            print(f"[operator] {line}", flush=True)
        for remaining in (3, 2, 1):
            print(f"[operator] capture begins in {remaining}...", flush=True)
            time.sleep(1.0)
        print("[operator] SPEAK NOW.", flush=True)


def _wait_for(predicate, timeout_s: float) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition was not reached")
