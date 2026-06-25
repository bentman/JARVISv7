from __future__ import annotations

import pytest

from backend.app.services.resident_voice_invocation import ResidentVoiceInvocationService


def _service() -> ResidentVoiceInvocationService:
    return ResidentVoiceInvocationService(
        session_service=object(),  # type: ignore[arg-type]
        engine_provider=lambda: object(),  # type: ignore[return-value]
    )


def test_resident_voice_mode_defaults_to_ptt_wake() -> None:
    service = _service()

    assert service.mode() == "ptt+wake"


def test_resident_voice_mode_changes_are_explicit_and_idempotent() -> None:
    service = _service()

    assert service.set_mode("ptt-only") == "ptt-only"
    assert service.set_mode("ptt-only") == "ptt-only"
    assert service.mode() == "ptt-only"
    assert service.set_mode("hands-free") == "hands-free"
    assert service.set_mode("continuous") == "continuous"
    assert service.set_mode("ptt+wake") == "ptt+wake"


def test_resident_voice_mode_rejects_unknown_values() -> None:
    service = _service()

    with pytest.raises(ValueError, match="unsupported resident voice mode"):
        service.set_mode("ambient")
