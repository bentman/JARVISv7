from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Protocol

import numpy as np


@dataclass(frozen=True, slots=True)
class WakeMonitorStatus:
    provider: str
    available: bool
    reason: str
    active: bool = False
    enabled: bool = False
    monitoring: bool = False
    last_detected: str | None = None
    detection_count: int = 0
    last_error: str | None = None
    last_score: float | None = None
    threshold: float | None = None


class WakeRuntime(Protocol):
    def is_available(self) -> bool:
        ...

    def detect(self, audio_chunk: np.ndarray) -> bool:
        ...


class WakeStatusStore:
    def __init__(self, *, provider: str, available: bool, reason: str) -> None:
        self._status = WakeMonitorStatus(provider=provider, available=available, reason=reason)

    def status(self) -> WakeMonitorStatus:
        return self._status

    def configure(self, *, provider: str, available: bool, reason: str) -> WakeMonitorStatus:
        if self._status.active or self._status.last_detected is not None or self._status.last_error is not None or "PTT-only fallback" in self._status.reason:
            return self._status
        self._status = WakeMonitorStatus(
            provider=provider,
            available=available,
            reason=reason,
            active=self._status.active,
            enabled=self._status.enabled,
            monitoring=False,
            last_detected=self._status.last_detected,
            detection_count=self._status.detection_count,
            last_error=self._status.last_error,
            last_score=self._status.last_score,
            threshold=self._status.threshold,
        )
        return self._status

    def start_monitor(self, *, provider: str, available: bool, reason: str) -> WakeMonitorStatus:
        if not available:
            return self.record_unavailable(reason or "wake runtime is unavailable; PTT-only fallback is active")
        self._status = WakeMonitorStatus(
            provider=provider,
            available=True,
            reason=reason,
            active=True,
            enabled=True,
            monitoring=True,
            last_detected=self._status.last_detected,
            detection_count=self._status.detection_count,
            last_error=None,
            last_score=self._status.last_score,
            threshold=self._status.threshold,
        )
        return self._status

    def stop_monitor(self, reason: str = "wake monitoring stopped; manual PTT is active") -> WakeMonitorStatus:
        self._status = WakeMonitorStatus(
            provider=self._status.provider,
            available=self._status.available,
            reason=reason,
            active=False,
            enabled=False,
            monitoring=False,
            last_detected=self._status.last_detected,
            detection_count=self._status.detection_count,
            last_error=self._status.last_error,
            last_score=self._status.last_score,
            threshold=self._status.threshold,
        )
        return self._status

    def pause_monitor(self, reason: str = "wake monitoring paused for resident voice invocation") -> WakeMonitorStatus:
        self._status = WakeMonitorStatus(
            provider=self._status.provider,
            available=self._status.available,
            reason=reason,
            active=self._status.active,
            enabled=self._status.enabled,
            monitoring=False,
            last_detected=self._status.last_detected,
            detection_count=self._status.detection_count,
            last_error=self._status.last_error,
            last_score=self._status.last_score,
            threshold=self._status.threshold,
        )
        return self._status

    def record_detection(self, *, last_score: float | None = None, threshold: float | None = None) -> WakeMonitorStatus:
        self._status = WakeMonitorStatus(
            provider=self._status.provider,
            available=True,
            reason="wake detected",
            active=self._status.active,
            enabled=self._status.enabled,
            monitoring=self._status.monitoring,
            last_detected=datetime.now(timezone.utc).isoformat(),
            detection_count=self._status.detection_count + 1,
            last_error=None,
            last_score=last_score if last_score is not None else self._status.last_score,
            threshold=threshold if threshold is not None else self._status.threshold,
        )
        return self._status

    def record_idle(self, reason: str = "wake listening", *, last_score: float | None = None, threshold: float | None = None) -> WakeMonitorStatus:
        self._status = WakeMonitorStatus(
            provider=self._status.provider,
            available=True,
            reason=reason,
            active=self._status.active,
            enabled=self._status.enabled,
            monitoring=self._status.monitoring,
            last_detected=self._status.last_detected,
            detection_count=self._status.detection_count,
            last_error=None,
            last_score=last_score if last_score is not None else self._status.last_score,
            threshold=threshold if threshold is not None else self._status.threshold,
        )
        return self._status

    def record_unavailable(self, reason: str = "wake runtime is unavailable; PTT-only fallback is active") -> WakeMonitorStatus:
        self._status = WakeMonitorStatus(
            provider=self._status.provider,
            available=False,
            reason=reason,
            active=False,
            enabled=False,
            monitoring=False,
            last_detected=self._status.last_detected,
            detection_count=self._status.detection_count,
            last_error=None,
            last_score=self._status.last_score,
            threshold=self._status.threshold,
        )
        return self._status

    def record_error(
        self,
        error: Exception | str,
        reason: str = "wake detection error; PTT-only fallback is active",
        *,
        last_score: float | None = None,
        threshold: float | None = None,
    ) -> WakeMonitorStatus:
        self._status = WakeMonitorStatus(
            provider=self._status.provider,
            available=False,
            reason=reason,
            active=False,
            enabled=False,
            monitoring=False,
            last_detected=self._status.last_detected,
            detection_count=self._status.detection_count,
            last_error=str(error),
            last_score=last_score if last_score is not None else self._status.last_score,
            threshold=threshold if threshold is not None else self._status.threshold,
        )
        return self._status

    def process_chunk(self, wake_runtime: WakeRuntime, audio_chunk: np.ndarray) -> WakeMonitorStatus:
        return self.process_chunks(wake_runtime, [audio_chunk])

    def process_chunks(self, wake_runtime: WakeRuntime, audio_chunks: Iterable[np.ndarray]) -> WakeMonitorStatus:
        if not wake_runtime.is_available():
            return self.record_unavailable()

        self._status = WakeMonitorStatus(
            provider=self._status.provider,
            available=True,
            reason=self._status.reason,
            active=self._status.active,
            enabled=self._status.enabled,
            monitoring=True,
            last_detected=self._status.last_detected,
            detection_count=self._status.detection_count,
            last_error=None,
            last_score=self._status.last_score,
            threshold=self._status.threshold,
        )
        try:
            for chunk in audio_chunks:
                if wake_runtime.detect(np.asarray(chunk)):
                    self.record_detection(
                        last_score=getattr(wake_runtime, "last_score", None),
                        threshold=getattr(wake_runtime, "threshold", None),
                    )
                    self._status = WakeMonitorStatus(
                        provider=self._status.provider,
                        available=self._status.available,
                        reason=self._status.reason,
                        active=self._status.active,
                        enabled=self._status.enabled,
                        monitoring=False,
                        last_detected=self._status.last_detected,
                        detection_count=self._status.detection_count,
                        last_error=self._status.last_error,
                        last_score=self._status.last_score,
                        threshold=self._status.threshold,
                    )
                    return self._status
                self.record_idle(
                    last_score=getattr(wake_runtime, "last_score", None),
                    threshold=getattr(wake_runtime, "threshold", None),
                )
        except Exception as exc:
            return self.record_error(
                exc,
                last_score=getattr(wake_runtime, "last_score", None),
                threshold=getattr(wake_runtime, "threshold", None),
            )

        self._status = WakeMonitorStatus(
            provider=self._status.provider,
            available=True,
            reason="wake not detected",
            active=self._status.active,
            enabled=self._status.enabled,
            monitoring=False,
            last_detected=self._status.last_detected,
            detection_count=self._status.detection_count,
            last_error=None,
            last_score=self._status.last_score,
            threshold=self._status.threshold,
        )
        return self._status
