from __future__ import annotations

import pytest

from backend.tests.conftest import SKIP_UNLESS_LIVE


@pytest.mark.live
@pytest.mark.turn
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_resident_barge_in_live_operator_gate() -> None:
    pytest.skip("operator-gated live barge-in proof requires coordinated microphone and TTS playback")
