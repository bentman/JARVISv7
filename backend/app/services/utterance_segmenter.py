from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np
from backend.app.runtimes.vad import VADRuntime
from backend.app.services.audio_stream import AudioChunk


@dataclass(frozen=True, slots=True)
class UtteranceDiagnostics:
    reason: str
    chunks: int
    speech_chunks: int
    sample_count: int
    duration_s: float
    rms: float
    peak: float
    max_chunk_rms: float
    max_chunk_peak: float

    def as_dict(self) -> dict[str, float | int | str]:
        return {
            "reason": self.reason,
            "chunks": self.chunks,
            "speech_chunks": self.speech_chunks,
            "sample_count": self.sample_count,
            "duration_s": self.duration_s,
            "rms": self.rms,
            "peak": self.peak,
            "max_chunk_rms": self.max_chunk_rms,
            "max_chunk_peak": self.max_chunk_peak,
        }


@dataclass(frozen=True, slots=True)
class UtteranceSegment:
    audio: np.ndarray
    sample_rate: int
    speech_started: bool
    reason: str
    chunks: int
    speech_chunks: int
    diagnostics: UtteranceDiagnostics


@dataclass(frozen=True, slots=True)
class UtteranceSegmenter:
    vad: VADRuntime
    sample_rate: int = 16000
    pre_roll_s: float = 0.25
    min_speech_s: float = 0.2
    silence_end_s: float = 0.4
    max_duration_s: float = 8.0
    no_speech_timeout_s: float = 3.0

    def capture(self, chunks: Iterable[AudioChunk]) -> UtteranceSegment:
        pre_roll_samples = self._seconds_to_samples(self.pre_roll_s)
        min_speech_samples = self._seconds_to_samples(self.min_speech_s)
        silence_end_samples = self._seconds_to_samples(self.silence_end_s)
        max_samples = self._seconds_to_samples(self.max_duration_s)
        no_speech_samples = self._seconds_to_samples(self.no_speech_timeout_s)

        pre_roll: deque[np.ndarray] = deque()
        pre_roll_total = 0
        collected: list[np.ndarray] = []
        speech_started = False
        speech_samples = 0
        silence_after_speech = 0
        total_seen = 0
        chunk_count = 0
        speech_chunk_count = 0
        seen_parts: list[np.ndarray] = []
        max_chunk_rms = 0.0
        max_chunk_peak = 0.0

        for chunk in chunks:
            samples = np.asarray(chunk.samples, dtype=np.float32).reshape(-1)
            if samples.size == 0:
                continue
            chunk_count += 1
            total_seen += int(samples.size)
            seen_parts.append(samples)
            chunk_rms = self._rms(samples)
            chunk_peak = self._peak(samples)
            max_chunk_rms = max(max_chunk_rms, chunk_rms)
            max_chunk_peak = max(max_chunk_peak, chunk_peak)
            decision = self.vad.detect(samples, chunk.sample_rate)

            if not speech_started:
                if decision.speech:
                    speech_started = True
                    speech_chunk_count += 1
                    speech_samples += int(samples.size)
                    collected.extend(pre_roll)
                    collected.append(samples)
                    pre_roll.clear()
                    pre_roll_total = 0
                elif total_seen >= no_speech_samples:
                    audio = np.concatenate(seen_parts).astype(np.float32, copy=False) if seen_parts else np.array([], dtype=np.float32)
                    return UtteranceSegment(
                        audio=np.array([], dtype=np.float32),
                        sample_rate=self.sample_rate,
                        speech_started=False,
                        reason="no-speech",
                        chunks=chunk_count,
                        speech_chunks=0,
                        diagnostics=self._diagnostics(
                            audio,
                            "no-speech",
                            chunk_count,
                            0,
                            max_chunk_rms,
                            max_chunk_peak,
                        ),
                    )
                else:
                    pre_roll.append(samples)
                    pre_roll_total += int(samples.size)
                    while pre_roll_total > pre_roll_samples and pre_roll:
                        removed = pre_roll.popleft()
                        pre_roll_total -= int(removed.size)
                continue

            collected.append(samples)
            if decision.speech:
                speech_chunk_count += 1
                speech_samples += int(samples.size)
                silence_after_speech = 0
            else:
                silence_after_speech += int(samples.size)

            captured_samples = sum(int(part.size) for part in collected)
            if captured_samples >= max_samples:
                return self._segment(collected, "max-duration", chunk_count, speech_chunk_count, max_chunk_rms, max_chunk_peak)
            if speech_samples >= min_speech_samples and silence_after_speech >= silence_end_samples:
                return self._segment(collected, "silence", chunk_count, speech_chunk_count, max_chunk_rms, max_chunk_peak)

        if speech_started:
            reason = "stream-ended" if speech_samples >= min_speech_samples else "too-short"
            return self._segment(collected, reason, chunk_count, speech_chunk_count, max_chunk_rms, max_chunk_peak)
        audio = np.concatenate(seen_parts).astype(np.float32, copy=False) if seen_parts else np.array([], dtype=np.float32)
        return UtteranceSegment(
            audio=np.array([], dtype=np.float32),
            sample_rate=self.sample_rate,
            speech_started=False,
            reason="no-speech",
            chunks=chunk_count,
            speech_chunks=0,
            diagnostics=self._diagnostics(audio, "no-speech", chunk_count, 0, max_chunk_rms, max_chunk_peak),
        )

    def _segment(
        self,
        parts: list[np.ndarray],
        reason: str,
        chunks: int,
        speech_chunks: int,
        max_chunk_rms: float,
        max_chunk_peak: float,
    ) -> UtteranceSegment:
        audio = np.concatenate(parts).astype(np.float32, copy=False) if parts else np.array([], dtype=np.float32)
        return UtteranceSegment(
            audio=audio,
            sample_rate=self.sample_rate,
            speech_started=True,
            reason=reason,
            chunks=chunks,
            speech_chunks=speech_chunks,
            diagnostics=self._diagnostics(audio, reason, chunks, speech_chunks, max_chunk_rms, max_chunk_peak),
        )

    def _seconds_to_samples(self, seconds: float) -> int:
        return max(0, int(seconds * self.sample_rate))

    def _diagnostics(
        self,
        audio: np.ndarray,
        reason: str,
        chunks: int,
        speech_chunks: int,
        max_chunk_rms: float,
        max_chunk_peak: float,
    ) -> UtteranceDiagnostics:
        sample_count = int(audio.size)
        duration_s = sample_count / float(self.sample_rate) if self.sample_rate else 0.0
        return UtteranceDiagnostics(
            reason=reason,
            chunks=chunks,
            speech_chunks=speech_chunks,
            sample_count=sample_count,
            duration_s=duration_s,
            rms=self._rms(audio),
            peak=self._peak(audio),
            max_chunk_rms=max_chunk_rms,
            max_chunk_peak=max_chunk_peak,
        )

    def _rms(self, samples: np.ndarray) -> float:
        if samples.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(np.square(samples))))

    def _peak(self, samples: np.ndarray) -> float:
        if samples.size == 0:
            return 0.0
        return float(np.max(np.abs(samples)))
