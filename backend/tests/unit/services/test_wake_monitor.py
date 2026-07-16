from __future__ import annotations

import threading
import time
from pathlib import Path

import numpy as np
from backend.app.runtimes.vad import EnergyVADRuntime
from backend.app.services import wake_monitor
from backend.app.services.audio_stream import ResidentAudioStream
from backend.app.services.utterance_segmenter import UtteranceSegmenter
from backend.app.services.wake_monitor import WakeMonitorService
from backend.tests.unit.services.test_session_service import _FakeWakeRuntime, _service


def _wait_for(predicate, timeout_s: float = 1.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition was not reached")


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
    invocations: list[tuple[str, np.ndarray | None, int | None]] = []

    def source(stop_event):
        yield np.zeros(4)
        yield np.ones(4)
        for _ in range(40):
            yield np.ones(4)
        while not stop_event.is_set():
            time.sleep(0.01)

    def invoke(source_name: str, audio: np.ndarray | None = None, sample_rate: int | None = None) -> None:
        invocations.append((source_name, audio, sample_rate))

    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: _FakeWakeRuntime(detections=[False, True]),
        chunk_source=source,
        invocation_callback=invoke,
    )

    monitor.start()
    _wait_for(lambda: service.wake_status().detection_count == 1)
    status = service.wake_status()
    monitor.stop()

    assert status.last_detected is not None
    assert status.detection_count == 1
    assert status.threshold == 0.5
    assert len(invocations) == 1
    source_name, audio, sample_rate = invocations[0]
    assert source_name == "wake"
    assert sample_rate == 16000
    assert audio is not None
    assert audio.dtype == np.float32
    assert audio.size >= 8


def test_wake_monitor_excludes_detection_preroll_and_keeps_immediate_command(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "backend.app.services.wake_monitor._float_to_int16",
        lambda samples: (_ for _ in ()).throw(AssertionError("resident frames must use cached PCM16")),
    )
    service = _service(tmp_path)
    invocations: list[tuple[str, np.ndarray | None, int | None]] = []
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4, chunk_source_factory=_blocking_source)
    stream.start()

    def invoke(source_name: str, audio: np.ndarray | None = None, sample_rate: int | None = None) -> None:
        invocations.append((source_name, audio, sample_rate))

    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: _FakeWakeRuntime(detections=[False, True]),
        chunk_source=lambda stop_event: (_ for _ in ()).throw(AssertionError("shared stream should be used")),
        invocation_callback=invoke,
        resident_stream=stream,
        utterance_segmenter=_segmenter(),
    )

    monitor.start()
    _wait_for(lambda: stream.status().subscribers == 1)
    stream.publish_for_test(np.zeros(4, dtype=np.float32))
    stream.publish_for_test(np.full(4, 0.1, dtype=np.float32))
    stream.publish_for_test(np.full(4, 0.2, dtype=np.float32))
    stream.publish_for_test(np.full(4, 0.2, dtype=np.float32))
    stream.publish_for_test(np.zeros(4, dtype=np.float32))
    stream.publish_for_test(np.zeros(4, dtype=np.float32))
    published = stream.buffered_chunks()

    _wait_for(lambda: len(invocations) == 1)
    monitor.stop()
    stream.stop()

    source_name, audio, sample_rate = invocations[0]
    assert source_name == "wake"
    assert sample_rate == 16000
    assert audio is not None
    assert audio.dtype == np.float32
    assert np.array_equal(audio, np.concatenate([chunk.samples for chunk in published[1:4]]))
    assert np.array_equal(audio[:4], published[1].samples)
    assert np.array_equal(audio[4:8], published[2].samples)
    assert not np.array_equal(audio[:4], published[0].samples)
    assert stream.status().running is False
    diagnostics = service.status().voice_capture_diagnostics
    assert diagnostics is not None
    assert diagnostics["source"] == "wake"
    assert diagnostics["stage"] == "segment"
    assert diagnostics["reason"] == "silence"
    assert diagnostics["speech_chunks"] >= 1


def test_wake_monitor_does_not_start_competing_fallback_when_resident_stream_is_stopped(tmp_path: Path) -> None:
    service = _service(tmp_path)
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4)

    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: _FakeWakeRuntime(),
        chunk_source=lambda stop_event: (_ for _ in ()).throw(AssertionError("fallback source should not run")),
        resident_stream=stream,
        utterance_segmenter=_segmenter(),
    )

    status = monitor.start()

    assert status.available is False
    assert status.active is False
    assert status.monitoring is False
    assert status.reason == "resident audio stream is stopped; start resident voice stream before wake monitoring"


def test_wake_monitor_reports_no_speech_after_wake_from_vad_timeout(tmp_path: Path) -> None:
    service = _service(tmp_path)
    invocations: list[tuple[str, np.ndarray | None, int | None]] = []

    def source(stop_event):
        yield np.ones(4, dtype=np.int16)
        yield np.zeros(4, dtype=np.int16)
        yield np.zeros(4, dtype=np.int16)
        while not stop_event.is_set():
            time.sleep(0.01)

    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: _FakeWakeRuntime(detections=[True]),
        chunk_source=source,
        invocation_callback=lambda source_name, audio, sample_rate: invocations.append((source_name, audio, sample_rate)),
        utterance_segmenter=_segmenter(),
    )

    monitor.start()
    _wait_for(lambda: len(invocations) == 1)
    monitor.stop()

    assert invocations[0][0] == "wake"
    assert invocations[0][1] is not None
    assert invocations[0][1].size == 0
    assert invocations[0][2] == 16000
    assert service.status().voice_capture_diagnostics is not None
    assert service.status().voice_capture_diagnostics["reason"] == "no-speech"


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


def test_wake_pause_resume_does_not_stop_shared_resident_stream(tmp_path: Path) -> None:
    service = _service(tmp_path)
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4, chunk_source_factory=_blocking_source)
    stream.start()
    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: _FakeWakeRuntime(),
        resident_stream=stream,
    )

    monitor.start()
    _wait_for(lambda: stream.status().subscribers == 1)
    should_resume = monitor.pause_for_voice_invocation()
    paused = service.wake_status()

    assert should_resume is True
    assert paused.monitoring is False
    assert stream.status().running is True
    assert stream.status().subscribers == 0

    resumed = monitor.resume_after_voice_invocation(should_resume)
    _wait_for(lambda: stream.status().subscribers == 1)
    monitor.stop()
    stream.stop()

    assert resumed.active is True


def test_wake_monitor_start_resets_runtime(tmp_path: Path) -> None:
    service = _service(tmp_path)

    class RuntimeWithReset(_FakeWakeRuntime):
        def __init__(self):
            super().__init__()
            self.reset_called = False

        def reset(self):
            self.reset_called = True

    runtime = RuntimeWithReset()

    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: runtime,
        chunk_source=lambda stop: [np.zeros(4)],
    )

    monitor.start()
    assert runtime.reset_called is True
    monitor.stop()


def test_wake_monitor_debounces_identical_idle_status_until_bounded_refresh(
    monkeypatch,
    tmp_path: Path,
) -> None:
    service = _service(tmp_path)
    idle_calls: list[tuple[str, float | None, float | None]] = []
    original_record_idle = service.record_wake_idle

    def record_idle(reason="wake listening", *, last_score=None, threshold=None):
        idle_calls.append((reason, last_score, threshold))
        return original_record_idle(reason, last_score=last_score, threshold=threshold)

    service.record_wake_idle = record_idle  # type: ignore[method-assign]
    clock_values = iter((0.0, 0.2, 0.4, 0.6, 1.0, 1.1))
    monkeypatch.setattr(wake_monitor, "monotonic", lambda: next(clock_values, 1.1))
    runtime = _FakeWakeRuntime()
    monitor = WakeMonitorService(
        session_service=service,
        runtime_factory=lambda: runtime,
        chunk_source=lambda stop: [np.zeros(4, dtype=np.int16) for _ in range(5)],
    )

    monitor.start()
    _wait_for(lambda: monitor._thread is None)
    runtime.last_score = 0.3
    monitor._record_wake_idle_if_due(runtime)

    assert idle_calls == [
        ("wake listening", 0.2, 0.5),
        ("wake listening", 0.2, 0.5),
        ("wake listening", 0.3, 0.5),
    ]
    assert service.wake_status().last_score == 0.3
    assert service.wake_status().threshold == 0.5

