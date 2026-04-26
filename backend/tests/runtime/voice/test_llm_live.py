from __future__ import annotations

import os

import pytest

from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.tests.conftest import SKIP_UNLESS_LIVE, SKIP_UNLESS_OLLAMA


@pytest.mark.live
@pytest.mark.llm
@pytest.mark.requires_ollama
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_OLLAMA, reason="JARVISV7_OLLAMA_URL not set")
def test_llm_ollama_returns_valid_string_response_to_known_prompt():
    runtime = OllamaLLM(
        base_url=os.environ["JARVISV7_OLLAMA_URL"],
        model=os.getenv("OLLAMA_MODEL", "phi4-mini"),
    )

    assert runtime.is_available()
    response = runtime.generate("Reply with exactly: ready")

    assert isinstance(response, str)
    assert response.strip()