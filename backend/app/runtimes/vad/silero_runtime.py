from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from backend.app.models.catalog import get_model_path
from backend.app.runtimes.vad.base import VADDecision

SILERO_MODEL_NAME = "silero-vad"
SILERO_MODEL_FILE = "silero_vad.onnx"
SILERO_MODEL_URL = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
SILERO_SAMPLE_RATE = 16000
SILERO_WINDOW_SAMPLES = 512
SILERO_CONTEXT_SAMPLES = 64
SILERO_STATE_SHAPE = (2, 1, 128)


def default_silero_model_path() -> Path:
    return get_model_path("vad", SILERO_MODEL_NAME) / SILERO_MODEL_FILE


class SileroVADRuntime:
    """Silero VAD v5 ONNX runtime with hysteresis and internal 512-sample windowing.

    Consumers stream arbitrary chunk sizes (the resident stream uses 1280-sample
    chunks at 16 kHz); the model requires exactly 512-sample windows plus 64
    samples of context from the previous window and a recurrent state tensor.
    """

    def __init__(
        self,
        model_path: Path | None = None,
        threshold: float = 0.5,
        neg_threshold: float = 0.35,
    ) -> None:
        self.model_path = model_path or default_silero_model_path()
        self.threshold = threshold
        self.neg_threshold = neg_threshold
        self._session: Any = None
        self._state = np.zeros(SILERO_STATE_SHAPE, dtype=np.float32)
        self._context = np.zeros(SILERO_CONTEXT_SAMPLES, dtype=np.float32)
        self._buffer = np.array([], dtype=np.float32)
        self._speech = False
        self._last_probability = 0.0

    def is_available(self) -> bool:
        return self.unavailable_reason() is None

    def unavailable_reason(self) -> str | None:
        if not self.model_path.is_file():
            return (
                f"silero VAD model missing at {self.model_path}; "
                f"run scripts/ensure_models.py --family vad or download {SILERO_MODEL_URL}"
            )
        if _import_onnxruntime() is None:
            return "onnxruntime is not importable; provision an onnxruntime hardware extra"
        return None

    def reset(self) -> None:
        self._state = np.zeros(SILERO_STATE_SHAPE, dtype=np.float32)
        self._context = np.zeros(SILERO_CONTEXT_SAMPLES, dtype=np.float32)
        self._buffer = np.array([], dtype=np.float32)
        self._speech = False
        self._last_probability = 0.0

    def detect(self, samples: np.ndarray, sample_rate: int) -> VADDecision:
        audio = np.asarray(samples, dtype=np.float32).reshape(-1)
        if audio.size == 0:
            return VADDecision(speech=False, probability=0.0, rms=0.0)
        if sample_rate != SILERO_SAMPLE_RATE:
            raise ValueError(
                f"SileroVADRuntime supports {SILERO_SAMPLE_RATE} Hz audio, got {sample_rate}"
            )
        rms = float(np.sqrt(np.mean(np.square(audio))))
        session = self._ensure_session()
        self._buffer = np.concatenate((self._buffer, audio))

        speech = self._speech
        probability = self._last_probability
        window_speech = False
        windows_processed = False
        while self._buffer.size >= SILERO_WINDOW_SAMPLES:
            window = self._buffer[:SILERO_WINDOW_SAMPLES]
            self._buffer = self._buffer[SILERO_WINDOW_SAMPLES:]
            window_probability = self._run_window(session, window)
            if window_probability >= self.threshold:
                self._speech = True
            elif window_probability < self.neg_threshold:
                self._speech = False
            window_speech = window_speech or self._speech
            if windows_processed:
                probability = max(probability, window_probability)
            else:
                probability = window_probability
            windows_processed = True
            self._last_probability = window_probability
        if windows_processed:
            speech = window_speech
        return VADDecision(speech=speech, probability=probability, rms=rms)

    def _run_window(self, session: Any, window: np.ndarray) -> float:
        frame = np.concatenate((self._context, window)).reshape(1, -1)
        outputs = session.run(
            None,
            {
                "input": frame,
                "state": self._state,
                "sr": np.array(SILERO_SAMPLE_RATE, dtype=np.int64),
            },
        )
        self._state = np.asarray(outputs[1], dtype=np.float32)
        self._context = window[-SILERO_CONTEXT_SAMPLES:].copy()
        return float(np.asarray(outputs[0]).reshape(-1)[0])

    def _ensure_session(self) -> Any:
        if self._session is not None:
            return self._session
        reason = self.unavailable_reason()
        if reason is not None:
            raise RuntimeError(reason)
        onnxruntime = _import_onnxruntime()
        options = onnxruntime.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        self._session = onnxruntime.InferenceSession(
            str(self.model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        return self._session


def _import_onnxruntime() -> Any:
    try:
        import onnxruntime
    except Exception:
        return None
    return onnxruntime
