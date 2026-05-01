from __future__ import annotations

from backend.app.core.settings import Settings
from backend.app.routing.runtime_selector import select_search_runtime
from backend.app.runtimes.internetsearch.ddgs_runtime import DDGSRuntime
from backend.app.runtimes.internetsearch.searxng_runtime import SearXNGRuntime
from backend.app.runtimes.internetsearch.tavily_runtime import TavilyRuntime


def _settings() -> Settings:
    return Settings()


def test_selector_prefers_searxng_then_ddgs_then_tavily_then_null() -> None:
    settings = _settings()
    settings.use_searxng = True
    settings.searxng_base_url = "http://searxng.test:18080"
    settings.use_ddgs = True
    settings.use_tavily = True
    settings.tavily_api_key = "key"

    runtime, trace = select_search_runtime(settings)
    assert runtime.runtime_name() == "searxng"
    assert trace.runtime_name == "searxng"

    settings.use_searxng = False
    runtime, trace = select_search_runtime(settings)
    assert runtime.runtime_name() == "ddgs"
    assert trace.runtime_name == "ddgs"

    settings.use_ddgs = False
    runtime, trace = select_search_runtime(settings)
    assert runtime.runtime_name() == "tavily"
    assert trace.runtime_name == "tavily"

    settings.use_tavily = False
    runtime, trace = select_search_runtime(settings)
    assert runtime.runtime_name() == "null"
    assert trace.runtime_name == "null"


def test_searxng_runtime_fail_closed_on_error(monkeypatch) -> None:
    settings = _settings()
    runtime = SearXNGRuntime(settings)

    def _boom(*args, **kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr("backend.app.runtimes.internetsearch.searxng_runtime.httpx.get", _boom)
    assert runtime.search("jarvis") == []


def test_ddgs_runtime_fail_closed_on_error(monkeypatch) -> None:
    settings = _settings()
    runtime = DDGSRuntime(settings)

    class _BrokenDDGS:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query, max_results=5):
            raise RuntimeError("provider down")

    monkeypatch.setattr("backend.app.runtimes.internetsearch.ddgs_runtime.DDGS", _BrokenDDGS)
    assert runtime.search("jarvis") == []


def test_tavily_runtime_disabled_without_key() -> None:
    settings = _settings()
    settings.use_tavily = True
    settings.tavily_api_key = ""
    runtime = TavilyRuntime(settings)

    assert runtime.is_available() is False
    assert runtime.search("jarvis") == []


def test_tavily_runtime_fail_closed_on_error(monkeypatch) -> None:
    settings = _settings()
    settings.use_tavily = True
    settings.tavily_api_key = "redacted"
    runtime = TavilyRuntime(settings)

    def _boom(*args, **kwargs):
        raise RuntimeError("external provider failed")

    monkeypatch.setattr("backend.app.runtimes.internetsearch.tavily_runtime.httpx.post", _boom)
    assert runtime.search("jarvis") == []


def test_runtime_result_mapping_shapes(monkeypatch) -> None:
    settings = _settings()
    settings.use_searxng = True
    settings.searxng_base_url = "http://searxng.test:18080"
    settings.use_ddgs = True

    searx = SearXNGRuntime(settings)

    class _Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"title": "a", "url": "u", "content": "c"}]}

    monkeypatch.setattr(
        "backend.app.runtimes.internetsearch.searxng_runtime.httpx.get",
        lambda *args, **kwargs: _Resp(),
    )
    searx_results = searx.search("jarvis")
    assert len(searx_results) == 1
    assert searx_results[0].source == "searxng"

    ddgs = DDGSRuntime(settings)

    class _DDGSClient:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def text(self, query, max_results=5):
            return [{"title": "b", "href": "u2", "body": "c2"}]

    monkeypatch.setattr("backend.app.runtimes.internetsearch.ddgs_runtime.DDGS", _DDGSClient)
    ddgs_results = ddgs.search("jarvis")
    assert len(ddgs_results) == 1
    assert ddgs_results[0].source == "ddgs"

    settings.use_tavily = True
    settings.tavily_api_key = "redacted"
    tavily = TavilyRuntime(settings)

    class _TResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"results": [{"title": "t", "url": "u3", "content": "c3"}]}

    monkeypatch.setattr(
        "backend.app.runtimes.internetsearch.tavily_runtime.httpx.post",
        lambda *args, **kwargs: _TResp(),
    )
    tavily_results = tavily.search("jarvis")
    assert len(tavily_results) == 1
    assert tavily_results[0].source == "tavily"
