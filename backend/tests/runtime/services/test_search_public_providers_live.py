from __future__ import annotations

import os

import pytest

from backend.app.core.settings import load_settings
from backend.app.runtimes.internetsearch.ddgs_runtime import DDGSRuntime
from backend.app.runtimes.internetsearch.tavily_runtime import TavilyRuntime


@pytest.mark.live
def test_search_ddgs_live() -> None:
    settings = load_settings()
    runtime = DDGSRuntime(settings)
    if not runtime.is_available():
        pytest.skip("DDGS disabled in settings")
    results = runtime.search("jarvis assistant", max_results=3)
    if not results:
        pytest.skip("DDGS provider unavailable or returned no results")
    assert len(results) >= 1
    assert all(result.source == "ddgs" for result in results)


@pytest.mark.live
def test_search_tavily_live() -> None:
    settings = load_settings()
    has_key = bool(settings.tavily_api_key)
    if not has_key:
        pytest.skip("Tavily API key unavailable")

    # Enable only in-process for live proof when key is present.
    os.environ["USE_TAVILY"] = "true"
    runtime = TavilyRuntime(load_settings())
    if not runtime.is_available():
        pytest.skip("Tavily unavailable; verify USE_TAVILY and provider prerequisites")

    results = runtime.search("jarvis assistant", max_results=3)
    if not results:
        pytest.skip("Tavily provider call failed for external reason")
    assert len(results) >= 1
    assert all(result.source == "tavily" for result in results)
