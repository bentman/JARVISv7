from __future__ import annotations

import numpy as np

from backend.app.services.wake_status import WakeStatusStore


class _WakeRuntime:
    def __init__(self, *, available: bool = True, detections: list[bool] | None = None, error: Exception | None = None) -> None:
        self.available = available
        self.detections = detections or []
        self.error = error
        self.last_score = 0.0
        self.threshold = 0.5

    def is_available(self) -> bool:
        return self.available

    def detect(self, audio_chunk: np.ndarray) -> bool:
        _ = audio_chunk
        if self.error is not None:
            self.last_score = 0.25
            raise self.error
        detected = self.detections.pop(0) if self.detections else False
        self.last_score = 0.8 if detected else 0.2
        return detected


def test_wake_status_store_preserves_detection_state_over_readiness_refresh() -> None:
    store = WakeStatusStore(provider="openwakeword", available=True, reason="wake ready")

    detected = store.process_chunk(_WakeRuntime(detections=[True]), np.zeros(4))
    refreshed = store.configure(provider="openwakeword", available=False, reason="wake unavailable")

    assert detected.reason == "wake detected"
    assert refreshed.reason == "wake detected"
    assert refreshed.available is True
    assert refreshed.detection_count == 1


def test_wake_status_store_records_unavailable_and_error_as_ptt_fallback() -> None:
    store = WakeStatusStore(provider="openwakeword", available=True, reason="wake ready")

    unavailable = store.process_chunk(_WakeRuntime(available=False), np.zeros(4))
    errored = store.record_error("mic failed")

    assert unavailable.reason == "wake runtime is unavailable; PTT-only fallback is active"
    assert unavailable.available is False
    assert errored.reason == "wake detection error; PTT-only fallback is active"
    assert errored.last_error == "mic failed"
