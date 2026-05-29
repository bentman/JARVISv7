from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


class AudioCaptureError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AudioIngressDiagnostics:
    usable: bool
    sample_rate: int
    sample_count: int
    dtype: str | None
    duration: float
    input_device: str | None
    rms: float
    peak: float
    reason: str


def capture_audio(duration_s: float, sample_rate: int = 16000) -> tuple[np.ndarray, int]:
    try:
        import sounddevice as sd

        frames = int(duration_s * sample_rate)
        audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
        sd.wait()
    except Exception as exc:
        raise AudioCaptureError(f"audio capture failed: {exc}") from exc
    return np.asarray(audio, dtype=np.float32).reshape(-1), sample_rate


def diagnose_audio_ingress(duration_s: float = 1.0) -> AudioIngressDiagnostics:
    capped_duration = min(max(float(duration_s), 0.1), 2.0)
    input_device = describe_input_device()
    try:
        audio, sample_rate = capture_audio(duration_s=capped_duration, sample_rate=16000)
    except Exception as exc:
        return AudioIngressDiagnostics(
            usable=False,
            sample_rate=16000,
            sample_count=0,
            dtype=None,
            duration=capped_duration,
            input_device=input_device,
            rms=0.0,
            peak=0.0,
            reason=f"capture failed: {exc}",
        )

    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    sample_count = int(samples.size)
    if sample_count == 0:
        return AudioIngressDiagnostics(
            usable=False,
            sample_rate=sample_rate,
            sample_count=0,
            dtype=str(np.asarray(audio).dtype),
            duration=0.0,
            input_device=input_device,
            rms=0.0,
            peak=0.0,
            reason="capture returned empty audio",
        )

    rms = float(np.sqrt(np.mean(np.square(samples))))
    peak = float(np.max(np.abs(samples)))
    actual_duration = sample_count / float(sample_rate) if sample_rate else 0.0
    if peak <= 1e-4 or rms <= 1e-5:
        return AudioIngressDiagnostics(
            usable=False,
            sample_rate=sample_rate,
            sample_count=sample_count,
            dtype=str(samples.dtype),
            duration=actual_duration,
            input_device=input_device,
            rms=rms,
            peak=peak,
            reason="capture succeeded but audio is silent",
        )

    return AudioIngressDiagnostics(
        usable=True,
        sample_rate=sample_rate,
        sample_count=sample_count,
        dtype=str(samples.dtype),
        duration=actual_duration,
        input_device=input_device,
        rms=rms,
        peak=peak,
        reason="capture succeeded with non-silent audio",
    )


def describe_input_device(sounddevice: Any | None = None) -> str | None:
    try:
        sd = sounddevice
        if sd is None:
            import sounddevice as sd
        default_device = getattr(sd, "default").device
        input_index = default_device[0] if isinstance(default_device, (list, tuple)) else default_device
        if input_index is None or input_index == -1:
            return "sounddevice default input"
        info = sd.query_devices(input_index, "input")
        name = info.get("name") if isinstance(info, dict) else getattr(info, "name", None)
        return f"{input_index}: {name}" if name else str(input_index)
    except Exception as exc:
        return f"sounddevice input device unknown: {exc}"
