from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import yaml

from backend.app.core.capabilities import HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from backend.app.hardware.readiness import derive_tts_device_readiness
from backend.app.models.catalog import catalog_path, get_model_entry, load_catalog
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


def tts_voice_config() -> dict[str, object]:
    entry = get_model_entry("tts")
    return _voice_payload(entry.name, entry.config)


def set_tts_voice(voice: str) -> dict[str, object]:
    selected_voice = voice.strip()
    catalog = load_catalog("tts")
    model_name = _default_model_name(catalog)
    models = catalog.get("models")
    if not isinstance(models, dict):
        raise ValueError("tts model catalog has invalid models section")
    model_config = models.get(model_name)
    if not isinstance(model_config, dict):
        raise ValueError(f"tts model catalog has invalid model entry: {model_name}")
    supported = _supported_voices(model_config)
    if selected_voice not in supported:
        raise ValueError(f"unsupported tts voice: {selected_voice}")
    model_config["voice"] = selected_voice
    path = catalog_path("tts")
    path.write_text(yaml.safe_dump(catalog, sort_keys=False), encoding="utf-8")
    return _voice_payload(model_name, model_config)


def _default_model_name(catalog: dict[str, Any]) -> str:
    model_name = catalog.get("default_model")
    if not isinstance(model_name, str) or not model_name.strip():
        raise ValueError("tts model catalog has no default_model")
    return model_name.strip()


def _supported_voices(model_config: dict[str, Any]) -> list[str]:
    supported = model_config.get("supported_voices")
    if not isinstance(supported, list):
        return []
    return [voice.strip() for voice in supported if isinstance(voice, str) and voice.strip()]


def _voice_payload(model_name: str, model_config: dict[str, Any]) -> dict[str, object]:
    configured = model_config.get("voice")
    voice = configured.strip() if isinstance(configured, str) and configured.strip() else ""
    return {
        "model": model_name,
        "voice": voice,
        "supported_voices": _supported_voices(model_config),
        "restart_required": True,
    }
