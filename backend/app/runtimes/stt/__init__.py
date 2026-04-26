from __future__ import annotations

from backend.app.runtimes.stt.base import STTBase
from backend.app.runtimes.stt.onnx_whisper_runtime import OnnxWhisperRuntime
from backend.app.runtimes.stt.stt_runtime import DegradedSTTRuntime, select_stt_runtime

__all__ = ["DegradedSTTRuntime", "OnnxWhisperRuntime", "STTBase", "select_stt_runtime"]