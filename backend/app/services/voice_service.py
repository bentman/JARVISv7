from __future__ import annotations

import numpy as np


class AudioCaptureError(RuntimeError):
    pass


def capture_audio(duration_s: float, sample_rate: int = 16000) -> tuple[np.ndarray, int]:
    try:
        import sounddevice as sd

        frames = int(duration_s * sample_rate)
        audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
        sd.wait()
    except Exception as exc:
        raise AudioCaptureError(f"audio capture failed: {exc}") from exc
    return np.asarray(audio, dtype=np.float32).reshape(-1), sample_rate