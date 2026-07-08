from __future__ import annotations

from pathlib import Path

import numpy as np

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.hardware.readiness import derive_tts_device_readiness
from backend.app.models.catalog import get_model_entry
from backend.app.runtimes.tts.base import TTSBase
from backend.app.runtimes.tts.kokoro_onnx_runtime import KOKORO_SAMPLE_RATE, KokoroOnnxRuntime


class NullTTSRuntime(TTSBase):
    def __init__(
        self,
        reason: str,
        device: str = "cpu",
        model_path: Path | None = None,
        sample_rate: int = KOKORO_SAMPLE_RATE,
    ) -> None:
        super().__init__(device=device, model_path=model_path or Path("."))
        self.reason = reason
        self._sample_rate = sample_rate

    def is_available(self) -> bool:
        return False

    def synthesize(self, text: str) -> np.ndarray:
        return np.array([], dtype=np.float32)

    def sample_rate(self) -> int:
        return self._sample_rate


def select_tts_runtime(preflight: PreflightResult, profile: HardwareProfile) -> TTSBase:
    device, ready, reason = derive_tts_device_readiness(preflight, profile)
    if not ready:
        return NullTTSRuntime(reason=reason, device=device)
    model_entry = get_model_entry("tts")
    configured_voice = model_entry.config.get("voice")
    if isinstance(configured_voice, str) and configured_voice.strip():
        return KokoroOnnxRuntime(device=device, voice=configured_voice.strip())
    return KokoroOnnxRuntime(device=device)


def tts_voice_config(active_voice: str | None = None) -> dict[str, object]:
    entry = get_model_entry("tts")
    return _voice_payload(entry.name, entry.config, active_voice=active_voice)


def validate_tts_voice(voice: str) -> str:
    selected_voice = voice.strip()
    entry = get_model_entry("tts")
    supported = _supported_voices(entry.config)
    if selected_voice not in supported:
        raise ValueError(f"unsupported tts voice: {selected_voice}")
    return selected_voice


def _supported_voices(model_config: dict[str, object]) -> list[str]:
    supported = model_config.get("supported_voices")
    if not isinstance(supported, list):
        return []
    return [voice.strip() for voice in supported if isinstance(voice, str) and voice.strip()]


def _voice_payload(
    model_name: str,
    model_config: dict[str, object],
    *,
    active_voice: str | None = None,
) -> dict[str, object]:
    configured = model_config.get("voice")
    baseline_voice = configured.strip() if isinstance(configured, str) and configured.strip() else ""
    active = active_voice.strip() if isinstance(active_voice, str) and active_voice.strip() else ""
    return {
        "model": model_name,
        "voice": active or baseline_voice,
        "baseline_voice": baseline_voice,
        "supported_voices": _supported_voices(model_config),
        "restart_required": False,
    }
