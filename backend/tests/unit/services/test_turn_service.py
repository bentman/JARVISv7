from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from backend.app.services.task_service import submit_text
from backend.app.services.turn_service import run_text_turn, run_voice_turn


def test_run_text_turn_delegates_to_engine():
    expected = object()
    engine = SimpleNamespace(run_text_turn=lambda text: expected)

    assert run_text_turn("hello", engine=engine) is expected


def test_run_voice_turn_delegates_to_engine():
    expected = object()
    engine = SimpleNamespace(run_voice_turn=lambda audio, sample_rate: expected)

    assert run_voice_turn(np.zeros(2, dtype=np.float32), 16000, engine=engine) is expected


def test_submit_text_rejects_empty_text():
    with pytest.raises(ValueError, match="non-empty"):
        submit_text("   ", engine=SimpleNamespace())


def test_submit_text_delegates_to_turn_service_path():
    expected = object()
    engine = SimpleNamespace(run_text_turn=lambda text: expected)

    assert submit_text("hello", engine=engine) is expected