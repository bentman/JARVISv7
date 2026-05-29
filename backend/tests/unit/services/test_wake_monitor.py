from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from backend.app.services.session_service import SessionService
from backend.app.services.wake_monitor import WakeMonitorService
from backend.tests.unit.services.test_session_service import _FakeWakeRuntime, _service


def _wait_for(predicate, timeout_s: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached")


def test_wake_monitor_start_stop_tracks_resident_state(tmp_path: Path) -> None:
    service = _service(tmp_path)

    def source(stop_event):
        while not stop_event.is_set():
            time.sleep(0.01)
            yield np.zeros(4)

    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: _FakeWakeRuntime(),
        chunk_source=source,
    )

    started = monitor.start()
    assert started.active is True
    assert started.enabled is True
    assert started.monitoring is True

    stopped = monitor.stop()
    assert stopped.available is True
    assert stopped.active is False
    assert stopped.enabled is False
    assert stopped.monitoring is False


def test_wake_monitor_detection_updates_count_and_timestamp(tmp_path: Path) -> None:
    service = _service(tmp_path)
    invocations: list[str] = []

    def source(stop_event):
        yield np.zeros(4)
        yield np.ones(4)
        while not stop_event.is_set():
            time.sleep(0.01)

    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: _FakeWakeRuntime(detections=[False, True]),
        chunk_source=source,
        invocation_callback=invocations.append,
    )

    monitor.start()
    _wait_for(lambda: service.wake_status().detection_count == 1)
    status = service.wake_status()
    monitor.stop()

    assert status.reason == "wake detected"
    assert status.last_detected is not None
    assert status.detection_count == 1
    assert status.last_score == 0.8
    assert status.threshold == 0.5
    assert invocations == ["wake"]


def test_wake_monitor_unavailable_runtime_fails_closed(tmp_path: Path) -> None:
    service = _service(tmp_path)
    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: _FakeWakeRuntime(available=False),
        chunk_source=lambda stop_event: iter([np.zeros(4)]),
    )

    status = monitor.start()

    assert status.available is False
    assert status.active is False
    assert status.enabled is False
    assert status.monitoring is False
    assert status.reason == "wake runtime is unavailable; PTT-only fallback is active"


def test_wake_monitor_capture_error_disables_monitoring(tmp_path: Path) -> None:
    service = _service(tmp_path)

    def source(stop_event):
        _ = stop_event
        raise RuntimeError("mic failed")
        yield np.zeros(4)

    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: _FakeWakeRuntime(),
        chunk_source=source,
    )

    monitor.start()
    _wait_for(lambda: service.wake_status().last_error == "mic failed")
    status = service.wake_status()

    assert status.available is False
    assert status.active is False
    assert status.enabled is False
    assert status.monitoring is False
    assert status.reason == "wake detection error; PTT-only fallback is active"
    assert status.last_error == "mic failed"
    assert status.last_score == 0.0
    assert status.threshold == 0.5


def test_wake_monitor_toggle_starts_and_stops(tmp_path: Path) -> None:
    service = _service(tmp_path)

    def source(stop_event):
        while not stop_event.is_set():
            time.sleep(0.01)
            yield np.zeros(4)

    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: _FakeWakeRuntime(),
        chunk_source=source,
    )

    assert monitor.toggle().active is True
    assert monitor.toggle().active is False


def test_wake_monitor_can_pause_for_resident_voice_and_resume(tmp_path: Path) -> None:
    service = _service(tmp_path)

    def source(stop_event):
        while not stop_event.is_set():
            time.sleep(0.01)
            yield np.zeros(4)

    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: _FakeWakeRuntime(),
        chunk_source=source,
    )

    monitor.start()
    should_resume = monitor.pause_for_voice_invocation()
    paused = service.wake_status()

    assert should_resume is True
    assert paused.active is True
    assert paused.monitoring is False
    assert paused.reason == "wake monitoring paused for resident voice invocation"

    resumed = monitor.resume_after_voice_invocation(should_resume)
    assert resumed.active is True
    assert resumed.monitoring is True

