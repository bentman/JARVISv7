from __future__ import annotations

import os

import pytest

from backend.tests.conftest import SKIP_UNLESS_LIVE


SKIP_UNLESS_RESIDENT_BARGE_IN_OPERATOR = not os.getenv("JARVISV7_RESIDENT_BARGE_IN_LIVE")


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(
    SKIP_UNLESS_RESIDENT_BARGE_IN_OPERATOR,
    reason="resident live barge-in microphone/TTS/operator gate JARVISV7_RESIDENT_BARGE_IN_LIVE not set",
)
def test_resident_barge_in_live_operator_gate() -> None:
    pytest.skip("operator-gated live barge-in proof requires coordinated microphone and TTS playback")
