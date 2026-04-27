from __future__ import annotations

import numpy as np

from backend.app.conversation.engine import TurnEngine, TurnResult


def run_voice_turn(audio: np.ndarray, sample_rate: int, *, engine: TurnEngine) -> TurnResult:
    return engine.run_voice_turn(audio, sample_rate)


def run_text_turn(text: str, *, engine: TurnEngine) -> TurnResult:
    return engine.run_text_turn(text)