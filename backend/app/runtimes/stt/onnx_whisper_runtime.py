from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from backend.app.hardware.qnn_provider import create_qnn_session
from backend.app.models.catalog import get_model_path
from backend.app.runtimes.stt.base import STTBase


QNN_STT_DEFERRED_REASON = "QNN STT inference deferred to H.2"


def providers_for_device(device: str) -> list[str]:
    if device == "cpu":
        return ["CPUExecutionProvider"]
    if device == "cuda":
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    if device == "directml":
        return ["DmlExecutionProvider", "CPUExecutionProvider"]
    if device == "qnn":
        return []
    raise ValueError(f"unsupported STT device '{device}'")


class OnnxWhisperRuntime(STTBase):
    def __init__(
        self,
        device: str = "cpu",
        model_path: Path | None = None,
        model_name: str = "whisper-small-onnx",
    ) -> None:
        super().__init__(device=device, model_path=model_path or get_model_path("stt", model_name))
        self.model_name = model_name
        self.providers = providers_for_device(device)
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self.device == "qnn":
            raise NotImplementedError(QNN_STT_DEFERRED_REASON)
        if self._model is None:
            import onnx_asr

            self._model = onnx_asr.load_model(
                "onnx-community/whisper-small",
                path=self.model_path,
                providers=self.providers,
            )
        return self._model

    def is_available(self) -> bool:
        if self.device == "qnn":
            return False
        required = (
            "encoder_model.onnx",
            "decoder_model_merged.onnx",
            "config.json",
            "generation_config.json",
            "preprocessor_config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "special_tokens_map.json",
            "vocab.json",
            "merges.txt",
            "normalizer.json",
            "added_tokens.json",
        )
        return all((self.model_path / filename).is_file() for filename in required)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        if self.device == "qnn":
            raise NotImplementedError(QNN_STT_DEFERRED_REASON)
        if not self.is_available():
            raise RuntimeError(f"STT model files are unavailable at {self.model_path}")
        waveform = np.asarray(audio, dtype=np.float32)
        result = self._load_model().recognize(waveform, sample_rate=sample_rate)
        if isinstance(result, str):
            return result
        return str(result)


class QnnWhisperRuntime(STTBase):
    """QNN-accelerated Whisper STT runtime for Snapdragon X Elite and compatible targets.

    Uses precompiled QNN context binaries paired with ONNX model files.
    Requires onnxruntime-qnn package and QAIRT SDK for QNN execution provider.
    """

    def __init__(
        self,
        device: str = "qnn",
        model_path: Path | None = None,
        model_name: str = "whisper-tiny-qnn-precompiled-snapdragon-x-elite",
    ) -> None:
        if device != "qnn":
            raise ValueError(f"QnnWhisperRuntime requires device='qnn', got '{device}'")
        super().__init__(device=device, model_path=model_path or get_model_path("stt", model_name))
        self.model_name = model_name
        self._encoder_session: Any | None = None
        self._decoder_session: Any | None = None

    def _find_model_file(self, filename: str) -> Path:
        """Find required model file by name (handles nested directories)."""
        candidates = sorted(path for path in self.model_path.rglob(filename) if path.is_file())
        if not candidates:
            raise FileNotFoundError(f"missing required model file '{filename}' under {self.model_path}")
        return candidates[0]

    def _load_encoder_session(self) -> Any:
        """Load encoder session with QNN provider."""
        if self._encoder_session is None:
            encoder_path = self._find_model_file("encoder.onnx")
            self._encoder_session, _ = create_qnn_session(encoder_path, disable_cpu_fallback=True)
        return self._encoder_session

    def _load_decoder_session(self) -> Any:
        """Load decoder session with QNN provider."""
        if self._decoder_session is None:
            decoder_path = self._find_model_file("decoder.onnx")
            self._decoder_session, _ = create_qnn_session(decoder_path, disable_cpu_fallback=True)
        return self._decoder_session

    def is_available(self) -> bool:
        """Check if all required model files are present."""
        required = (
            "encoder.onnx",
            "decoder.onnx",
        )
        return all(any(path.is_file() for path in self.model_path.rglob(filename)) for filename in required)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        """Transcribe audio using QNN-accelerated Whisper encoder/decoder.

        This placeholder defers full transcription logic to future slice.
        Current implementation validates encoder/decoder session initialization.
        """
        if not self.is_available():
            raise RuntimeError(f"STT model files are unavailable at {self.model_path}")

        # Validate sessions load correctly (this proves QNN provider works)
        _ = self._load_encoder_session()
        _ = self._load_decoder_session()

        # Full transcription (audio preprocessing, tokenization, decoder loop)
        # deferred to H.2 when inference logic is implemented
        raise NotImplementedError("QNN Whisper transcription deferred to H.3.2")