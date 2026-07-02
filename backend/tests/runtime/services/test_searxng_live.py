from __future__ import annotations

import pytest

from backend.app.core.settings import load_settings
from backend.app.runtimes.internetsearch.searxng_runtime import SearXNGRuntime


@pytest.mark.live
@pytest.mark.requires_docker
@pytest.mark.requires_searxng
def test_search_searxng_live() -> None:
    settings = load_settings()
    runtime = SearXNGRuntime(settings)
    if not runtime.is_available():
        pytest.skip("SearXNG disabled in settings")
    results = runtime.search("jarvis assistant", max_results=3)
    if not results:
        pytest.skip("SearXNG unavailable or returned no results")
    assert len(results) >= 1
    assert all(result.source == "searxng" for result in results)
