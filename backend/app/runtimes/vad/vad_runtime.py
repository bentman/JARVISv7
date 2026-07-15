from __future__ import annotations

import logging
from pathlib import Path

from backend.app.core.settings import Settings
from backend.app.runtimes.vad.base import VADRuntime
from backend.app.runtimes.vad.energy_runtime import EnergyVADRuntime
from backend.app.runtimes.vad.silero_runtime import SileroVADRuntime

_LOGGER = logging.getLogger(__name__)


def select_vad_runtime(settings: Settings, model_path: Path | None = None) -> tuple[VADRuntime, str]:
    """Select the resident-voice VAD runtime and report the selection reason.

    RESIDENT_VOICE_VAD: "auto" (silero when the model is present, else energy),
    "silero" (silero, or energy with a degraded reason), "energy" (always energy).
    """
    energy = EnergyVADRuntime(speech_rms_threshold=settings.resident_voice_speech_rms_threshold)
    mode = settings.resident_voice_vad
    if mode == "energy":
        reason = "energy VAD selected by RESIDENT_VOICE_VAD=energy"
        _LOGGER.info(reason)
        return energy, reason
    silero = SileroVADRuntime(model_path=model_path)
    if silero.is_available():
        reason = f"silero VAD selected (RESIDENT_VOICE_VAD={mode}): {silero.model_path}"
        _LOGGER.info(reason)
        return silero, reason
    unavailable = silero.unavailable_reason() or "silero VAD unavailable"
    if mode == "silero":
        reason = f"RESIDENT_VOICE_VAD=silero degraded to energy VAD: {unavailable}"
        _LOGGER.warning(reason)
    else:
        reason = f"energy VAD fallback (RESIDENT_VOICE_VAD=auto): {unavailable}"
        _LOGGER.info(reason)
    return energy, reason
