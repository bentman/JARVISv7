from __future__ import annotations

import threading
import time
from types import SimpleNamespace

import numpy as np
import pytest

from backend.app.services.audio_stream import ResidentAudioStream
from backend.app.services.voice_service import capture_audio, wake_chunk_source


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


def test_stream_starts_stops_and_reports_status_with_fake_source() -> None:
    def source(stop_event: threading.Event):
        for index in range(2):
            if stop_event.is_set():
                break
            yield np.full(4, index, dtype=np.float32)

    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4, chunk_source_factory=source)

    status = stream.start()
    assert status.running is True

    _wait_for(lambda: stream.status().sequence == 2)
    stopped = stream.stop()

    assert stopped.running is False
    assert stopped.sample_rate == 16000
    assert stopped.chunk_samples == 4
    assert stopped.sequence == 2
    assert stopped.buffer_chunks == 2
    assert stopped.last_error is None


def test_stream_buffers_chunks_and_replays_to_new_subscriber() -> None:
    stream = ResidentAudioStream(buffer_chunks=2)

    stream.publish_for_test(np.array([1], dtype=np.float32))
    stream.publish_for_test(np.array([2], dtype=np.float32))
    stream.publish_for_test(np.array([3], dtype=np.float32))

    buffered = stream.buffered_chunks()
    replay = stream.subscribe(include_buffer=True)

    assert [chunk.sequence for chunk in buffered] == [2, 3]
    assert [replay.get_nowait().sequence, replay.get_nowait().sequence] == [2, 3]
    assert stream.status().subscribers == 1

    stream.unsubscribe(replay)
    assert stream.status().subscribers == 0


def test_stream_counts_dropped_chunks_for_full_subscriber_queue() -> None:
    stream = ResidentAudioStream(subscriber_queue_size=1)
    subscriber = stream.subscribe()

    stream.publish_for_test(np.array([1], dtype=np.float32))
    stream.publish_for_test(np.array([2], dtype=np.float32))

    assert subscriber.get_nowait().sequence == 1
    assert stream.status().dropped_chunks == 1


def test_one_stream_owner_model_is_explicit_in_status() -> None:
    stream = ResidentAudioStream(chunk_source_factory=_blocking_source)
    first = stream.start()
    second = stream.start()
    stopped = stream.stop()
    stopped_again = stream.stop()

    assert first.running is True
    assert second.running is True
    assert second.sequence == first.sequence
    assert stopped.running is False
    assert stopped_again.running is False


def test_capture_audio_can_read_from_running_resident_stream() -> None:
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4, chunk_source_factory=_blocking_source)
    subscriber_ready = threading.Event()

    def publish_after_subscribe() -> None:
        subscriber_ready.wait(timeout=1.0)
        stream.publish_for_test(np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32))

    original_subscribe = stream.subscribe

    def tracking_subscribe(*args, **kwargs):
        subscriber = original_subscribe(*args, **kwargs)
        subscriber_ready.set()
        return subscriber

    stream.subscribe = tracking_subscribe  # type: ignore[method-assign]
    stream.start()
    publisher = threading.Thread(target=publish_after_subscribe)
    publisher.start()

    audio, sample_rate = capture_audio(0.00025, sample_rate=16000, resident_stream=stream)

    publisher.join(timeout=1.0)
    stream.stop()
    assert sample_rate == 16000
    assert np.allclose(audio, np.array([0.1, 0.2, 0.3, 0.4], dtype=np.float32))


def test_capture_audio_falls_back_when_resident_stream_is_stopped(monkeypatch) -> None:
    stream = ResidentAudioStream()
    calls = []

    def fake_rec(frames, samplerate, channels, dtype):
        calls.append((frames, samplerate, channels, dtype))
        return np.zeros((frames, channels), dtype=np.float32)

    fake_sounddevice = SimpleNamespace(rec=fake_rec, wait=lambda: calls.append("wait"))
    monkeypatch.setitem(__import__("sys").modules, "sounddevice", fake_sounddevice)

    audio, sample_rate = capture_audio(0.1, sample_rate=16000, resident_stream=stream)

    assert sample_rate == 16000
    assert audio.shape == (1600,)
    assert calls == [(1600, 16000, 1, "float32"), "wait"]


def test_wake_chunk_source_can_read_from_running_resident_stream() -> None:
    stop_event = threading.Event()
    stream = ResidentAudioStream(sample_rate=16000, chunk_samples=4, chunk_source_factory=_blocking_source)
    stream.start()
    publisher_ready = threading.Event()

    source = wake_chunk_source(stop_event, resident_stream=stream)

    def publish_after_subscribe() -> None:
        publisher_ready.wait(timeout=1.0)
        stream.publish_for_test(np.array([5, 6, 7, 8], dtype=np.float32))

    original_subscribe = stream.subscribe

    def tracking_subscribe(*args, **kwargs):
        subscriber = original_subscribe(*args, **kwargs)
        publisher_ready.set()
        return subscriber

    stream.subscribe = tracking_subscribe  # type: ignore[method-assign]
    publisher = threading.Thread(target=publish_after_subscribe)
    publisher.start()
    chunk = next(iter(source))
    stop_event.set()
    publisher.join(timeout=1.0)
    stream.stop()

    assert np.array_equal(chunk, np.array([5, 6, 7, 8], dtype=np.float32))


def test_stream_records_source_errors() -> None:
    def source(_stop_event: threading.Event):
        raise RuntimeError("input failed")
        yield np.array([], dtype=np.float32)

    stream = ResidentAudioStream(chunk_source_factory=source)
    stream.start()

    _wait_for(lambda: stream.status().last_error == "input failed")
    status = stream.stop()

    assert status.last_error == "input failed"


def test_capture_audio_from_running_stream_times_out_without_chunks() -> None:
    stream = ResidentAudioStream(chunk_source_factory=_blocking_source)
    stream.start()

    with pytest.raises(Exception, match="resident audio stream timed out"):
        capture_audio(0.01, sample_rate=16000, resident_stream=stream)

    stream.stop()
