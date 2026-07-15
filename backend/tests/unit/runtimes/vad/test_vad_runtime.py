from __future__ import annotations

import numpy as np
from backend.app.runtimes.vad import EnergyVADRuntime, VADDecision


def test_energy_vad_reports_no_speech_for_empty_audio() -> None:
    decision = EnergyVADRuntime().detect(np.array([], dtype=np.float32), 16000)

    assert decision == VADDecision(speech=False, probability=0.0, rms=0.0)


def test_energy_vad_thresholds_silence_and_speech() -> None:
    vad = EnergyVADRuntime(speech_rms_threshold=0.05, probability_rms_scale=0.1)

    silence = vad.detect(np.zeros(8, dtype=np.float32), 16000)
    speech = vad.detect(np.full(8, 0.1, dtype=np.float32), 16000)

    assert silence.speech is False
    assert silence.probability == 0.0
    assert speech.speech is True
    assert speech.rms > 0.09
    assert speech.probability > 0.9


def test_t2_uses_dependency_free_energy_vad_without_model_artifact() -> None:
    vad = EnergyVADRuntime()

    assert vad.__class__.__module__ == "backend.app.runtimes.vad.energy_runtime"
    assert hasattr(vad, "detect")
