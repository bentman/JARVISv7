from __future__ import annotations

import pytest

from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.tests.conftest import (
    SKIP_UNLESS_LIVE,
    SKIP_UNLESS_OLLAMA,
    llama_cpp_base_url,
    llama_cpp_model_name,
    ollama_base_url,
)


def _live_llama_cpp_runtime() -> LlamaCppLLM:
    runtime = LlamaCppLLM(
        base_url=llama_cpp_base_url(),
        model=llama_cpp_model_name(),
        generation_defaults={"max_tokens": 16, "temperature": 0},
        managed=True,
    )
    if not runtime.is_available():
        pytest.skip(f"requires live llama.cpp sidecar: {runtime.reason}")
    return runtime


@pytest.mark.live
@pytest.mark.llm
@pytest.mark.requires_ollama
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_OLLAMA, reason="OLLAMA_BASE_URL not set")
def test_llm_ollama_returns_valid_string_response_to_known_prompt():
    runtime = OllamaLLM(
        base_url=ollama_base_url(),
    )

    assert runtime.is_available()
    response = runtime.generate("Reply with exactly: ready")

    assert isinstance(response, str)
    assert response.strip()


@pytest.mark.live
@pytest.mark.llm
@pytest.mark.requires_llama_cpp
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_llm_llama_cpp_sidecar_is_available():
    runtime = _live_llama_cpp_runtime()

    assert runtime.runtime_name() == "llama.cpp"
    assert runtime.reason in {
        "llama.cpp /v1/models reachable",
        "llama.cpp health endpoint reachable",
    }


@pytest.mark.live
@pytest.mark.llm
@pytest.mark.requires_llama_cpp
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_llm_llama_cpp_returns_valid_string_response_to_known_prompt():
    runtime = _live_llama_cpp_runtime()

    response = runtime.generate("Reply with exactly: ready")

    assert isinstance(response, str)
    assert response.strip()
