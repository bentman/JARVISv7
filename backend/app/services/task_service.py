from __future__ import annotations

from backend.app.conversation.engine import TurnEngine, TurnResult
from backend.app.services.turn_service import run_text_turn


def submit_text(text: str, *, engine: TurnEngine) -> TurnResult:
    if not text.strip():
        raise ValueError("text must be non-empty")
    return run_text_turn(text, engine=engine)