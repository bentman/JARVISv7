from __future__ import annotations

import pytest
from backend.app.core.settings import load_settings
from backend.app.runtimes.internetsearch.searxng_runtime import SearXNGRuntime


@pytest.mark.live
@pytest.mark.search
def test_search_searxng_live() -> None:
    settings = load_settings()
    runtime = SearXNGRuntime(settings)
    if not settings.use_searxng:
        pytest.skip("SearXNG disabled in settings")
    response = runtime.search("Python official documentation", max_results=3)
    assert response.status == "success", (response.status, response.reason)
    assert response.results
    assert all(result.source == "searxng" for result in response.results)
