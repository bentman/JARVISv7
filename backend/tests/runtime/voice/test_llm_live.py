from __future__ import annotations

import pytest

from backend.app.runtimes.llm.local_runtime import LlamaCppLLM
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.tests.conftest import (
    LLAMA_CPP_READY_PROMPT,
    SKIP_UNLESS_LIVE,
    SKIP_UNLESS_OLLAMA,
    assert_llama_cpp_ready_contract,
    ollama_base_url,
)


def _live_llama_cpp_runtime(live_llama_cpp_sidecar) -> LlamaCppLLM:
    resolution = live_llama_cpp_sidecar.resolution
    generation_defaults = {
        **resolution.generation_defaults,
        "max_tokens": 16,
        "temperature": 0,
    }
    runtime = LlamaCppLLM(
        base_url=resolution.base_url,
        model=resolution.model_id,
        sidecar_status=live_llama_cpp_sidecar.service.status,
        generation_defaults=generation_defaults,
        managed=True,
        route=resolution.route,
        serve_profile_id=resolution.serve_profile_id,
        accelerator=resolution.accelerator,
        selected_reason=resolution.selected_reason,
        model_mode=resolution.model_mode,
        model_policy=resolution.model_policy,
        model_role=resolution.model_role,
        model_selection_reason=resolution.model_selection_reason,
    )
    assert runtime.is_available(), runtime.reason
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

    if not runtime.is_available():
        pytest.skip(f"ollama live endpoint unavailable: {runtime.reason}")
    response = runtime.generate(LLAMA_CPP_READY_PROMPT)

    assert isinstance(response, str)
    assert response.strip()


@pytest.mark.live
@pytest.mark.llm
@pytest.mark.requires_llama_cpp
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_llm_llama_cpp_sidecar_is_available(live_llama_cpp_sidecar):
    runtime = _live_llama_cpp_runtime(live_llama_cpp_sidecar)
    resolution = live_llama_cpp_sidecar.resolution

    assert runtime.runtime_name() == "llama.cpp"
    assert runtime.reason in {
        "llama.cpp /v1/models reachable",
        "llama.cpp health endpoint reachable",
    }
    assert runtime.model == resolution.model_id
    assert runtime.model_mode == resolution.model_mode
    assert runtime.model_policy == resolution.model_policy
    assert runtime.model_role == resolution.model_role
    assert runtime.serve_profile_id == resolution.serve_profile_id
    assert runtime.accelerator == resolution.accelerator
    if runtime.model_mode == "prod":
        assert runtime.model != "assistant-small-q4"


@pytest.mark.live
@pytest.mark.llm
@pytest.mark.requires_llama_cpp
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_llm_llama_cpp_returns_deterministic_response_to_known_prompt(live_llama_cpp_sidecar):
    runtime = _live_llama_cpp_runtime(live_llama_cpp_sidecar)

    response = runtime.generate(LLAMA_CPP_READY_PROMPT)

    assert_llama_cpp_ready_contract(response, runtime=runtime)
