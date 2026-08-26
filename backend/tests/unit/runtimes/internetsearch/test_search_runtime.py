from __future__ import annotations

import httpx
import pytest
from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch.base import map_results, search_failure
from backend.app.runtimes.internetsearch.ddgs_runtime import DDGSRuntime
from backend.app.runtimes.internetsearch.searxng_runtime import SearXNGRuntime
from backend.app.runtimes.internetsearch.tavily_runtime import TavilyRuntime

pytestmark = pytest.mark.search


@pytest.mark.parametrize("runtime_type,flag", [(DDGSRuntime, "use_ddgs"), (SearXNGRuntime, "use_searxng"), (TavilyRuntime, "use_tavily")])
def test_disabled_providers_do_not_call_network(runtime_type, flag):
    settings = Settings()
    setattr(settings, flag, False)
    assert runtime_type(settings).search("public topic").status == "disabled"


@pytest.mark.parametrize("code,status", [(401, "misconfigured"), (403, "misconfigured"), (429, "rate_limited"), (500, "failed")])
def test_http_failures_are_distinct(code, status):
    response = httpx.Response(code, request=httpx.Request("GET", "https://example.com"))
    with pytest.raises(httpx.HTTPStatusError) as caught:
        response.raise_for_status()
    assert search_failure(caught.value).status == status
    assert search_failure(httpx.ReadTimeout("secret-bearing URL")).status == "timeout"


def test_malformed_results_are_not_success():
    assert map_results(None, "test", url_key="url", snippet_key="content", limit=5).status == "failed"
    assert map_results([None, {}, {"url": "u", "content": 3}], "test", url_key="url", snippet_key="content", limit=5).status == "empty"


def test_provider_payloads_and_bounds(monkeypatch):
    settings = Settings()
    settings.use_ddgs = settings.use_searxng = settings.use_tavily = True
    settings.tavily_api_key = "test-key"
    settings.searxng_base_url = "http://127.0.0.1:8888"
    calls = []

    class DDGSClient:
        def __init__(self, **kwargs):
            assert kwargs == {"timeout": 5, "verify": True}
        def __enter__(self):
            return self
        def __exit__(self, *_):
            pass
        def text(self, query, max_results):
            calls.append(("ddgs", query, max_results))
            return [{"title": "DDGS", "href": "https://example.com", "body": "excerpt"}]

    def get(url, **kwargs):
        assert url == settings.searxng_base_url + "/search"
        assert kwargs["params"] == {"q": "topic", "format": "json"}
        assert kwargs["timeout"] == 5
        return httpx.Response(200, json={"results": [{"title": "S", "url": "https://example.com", "content": "snippet"}]}, request=httpx.Request("GET", url))

    def post(url, **kwargs):
        assert kwargs["headers"] == {"Authorization": "Bearer test-key"}
        assert kwargs["json"] == {"query": "topic", "max_results": 5, "search_depth": "basic", "auto_parameters": False, "include_answer": False, "include_raw_content": False}
        assert kwargs["timeout"] == 8
        return httpx.Response(200, json={"results": [{"title": "T", "url": "https://example.com", "content": "snippet"}]}, request=httpx.Request("POST", url))

    monkeypatch.setattr("backend.app.runtimes.internetsearch.ddgs_runtime.DDGS", DDGSClient)
    monkeypatch.setattr("backend.app.runtimes.internetsearch.searxng_runtime.httpx.get", get)
    monkeypatch.setattr("backend.app.runtimes.internetsearch.tavily_runtime.httpx.post", post)
    for runtime in (DDGSRuntime(settings), SearXNGRuntime(settings), TavilyRuntime(settings)):
        result = runtime.search("topic", max_results=50)
        assert result.status == "success"
        assert result.results[0].source == runtime.runtime_name()
    assert calls == [("ddgs", "topic", 5)]
    settings.tavily_api_key = ""
    settings.searxng_base_url = ""
    assert TavilyRuntime(settings).search("topic").status == "misconfigured"
    assert SearXNGRuntime(settings).search("topic").status == "misconfigured"
