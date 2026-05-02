from __future__ import annotations

import numpy as np

from backend.app.conversation.engine import TurnEngine, TurnResult


def run_voice_turn(
    audio: np.ndarray,
    sample_rate: int,
    *,
    engine: TurnEngine,
    tool_name: str | None = None,
    tool_input: dict[str, object] | None = None,
) -> TurnResult:
    if tool_name is None and tool_input is None:
        return engine.run_voice_turn(audio, sample_rate)
    return engine.run_voice_turn(audio, sample_rate, tool_name=tool_name, tool_input=tool_input)


def run_text_turn(
    text: str,
    *,
    engine: TurnEngine,
    tool_name: str | None = None,
    tool_input: dict[str, object] | None = None,
) -> TurnResult:
    if tool_name is None and tool_input is None:
        return engine.run_text_turn(text)
    return engine.run_text_turn(text, tool_name=tool_name, tool_input=tool_input)