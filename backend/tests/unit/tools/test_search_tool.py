from __future__ import annotations

import json

from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch.base import SearchResult
from backend.app.tools.search import search_tool as mod


class _Runtime:
    def __init__(self, settings: Settings | None = None, *, name: str = "runtime", available: bool = True, raises: bool = False, empty: bool = False) -> None:
        _ = settings
        self.name = name
        self.available = available
        self.raises = raises
        self.empty = empty
        self.calls = 0

    def runtime_name(self) -> str:
        return self.name

    def is_available(self) -> bool:
        return self.available

    def search(self, query: str, *, max_results: int = 3):
        self.calls += 1
        if self.raises:
            raise RuntimeError("boom")
        if self.empty:
            return []
        return [SearchResult(title=f"{self.name}-title", url="u", snippet="s", source=self.name)]


def _patch_providers(monkeypatch, searx: _Runtime, ddgs: _Runtime, tavily: _Runtime) -> None:
    monkeypatch.setattr(mod, "SearXNGRuntime", lambda settings: searx)
    monkeypatch.setattr(mod, "DDGSRuntime", lambda settings: ddgs)
    monkeypatch.setattr(mod, "TavilyRuntime", lambda settings: tavily)


def test_search_tool_returns_json_results_on_searxng_success(monkeypatch) -> None:
    searx = _Runtime(name="searxng")
    ddgs = _Runtime(name="ddgs")
    tavily = _Runtime(name="tavily")
    _patch_providers(monkeypatch, searx, ddgs, tavily)

    out = mod.SearchTool(Settings()).run({"query": "jarvis", "max_results": 1})
    payload = json.loads(out)

    assert payload[0]["title"] == "searxng-title"
    assert payload[0]["source"] == "searxng"
    assert searx.calls == 1
    assert ddgs.calls == 0
    assert tavily.calls == 0


def test_search_tool_falls_back_to_ddgs_when_searxng_empty(monkeypatch) -> None:
    searx = _Runtime(name="searxng", empty=True)
    ddgs = _Runtime(name="ddgs")
    tavily = _Runtime(name="tavily")
    _patch_providers(monkeypatch, searx, ddgs, tavily)

    payload = json.loads(mod.SearchTool(Settings()).run({"query": "jarvis"}))

    assert payload[0]["source"] == "ddgs"
    assert searx.calls == 1
    assert ddgs.calls == 1
    assert tavily.calls == 0


def test_search_tool_falls_back_to_ddgs_when_searxng_raises(monkeypatch) -> None:
    searx = _Runtime(name="searxng", raises=True)
    ddgs = _Runtime(name="ddgs")
    tavily = _Runtime(name="tavily")
    _patch_providers(monkeypatch, searx, ddgs, tavily)

    payload = json.loads(mod.SearchTool(Settings()).run({"query": "jarvis"}))

    assert payload[0]["source"] == "ddgs"
    assert searx.calls == 1
    assert ddgs.calls == 1
    assert tavily.calls == 0


def test_search_tool_falls_back_to_tavily_when_ddgs_empty(monkeypatch) -> None:
    searx = _Runtime(name="searxng", empty=True)
    ddgs = _Runtime(name="ddgs", empty=True)
    tavily = _Runtime(name="tavily")
    _patch_providers(monkeypatch, searx, ddgs, tavily)

    payload = json.loads(mod.SearchTool(Settings()).run({"query": "jarvis"}))

    assert payload[0]["source"] == "tavily"
    assert searx.calls == 1
    assert ddgs.calls == 1
    assert tavily.calls == 1


def test_search_tool_falls_back_to_tavily_when_ddgs_raises(monkeypatch) -> None:
    searx = _Runtime(name="searxng", empty=True)
    ddgs = _Runtime(name="ddgs", raises=True)
    tavily = _Runtime(name="tavily")
    _patch_providers(monkeypatch, searx, ddgs, tavily)

    payload = json.loads(mod.SearchTool(Settings()).run({"query": "jarvis"}))

    assert payload[0]["source"] == "tavily"
    assert searx.calls == 1
    assert ddgs.calls == 1
    assert tavily.calls == 1


def test_search_tool_skips_unavailable_providers(monkeypatch) -> None:
    searx = _Runtime(name="searxng", available=False)
    ddgs = _Runtime(name="ddgs")
    tavily = _Runtime(name="tavily")
    _patch_providers(monkeypatch, searx, ddgs, tavily)

    payload = json.loads(mod.SearchTool(Settings()).run({"query": "jarvis"}))

    assert payload[0]["source"] == "ddgs"
    assert searx.calls == 0
    assert ddgs.calls == 1
    assert tavily.calls == 0


def test_search_tool_returns_empty_json_when_no_provider(monkeypatch) -> None:
    _patch_providers(
        monkeypatch,
        _Runtime(name="searxng", empty=True),
        _Runtime(name="ddgs", empty=True),
        _Runtime(name="tavily", empty=True),
    )
    assert mod.SearchTool(Settings()).run({"query": "jarvis"}) == "[]"


def test_search_tool_does_not_raise_on_runtime_error(monkeypatch) -> None:
    _patch_providers(
        monkeypatch,
        _Runtime(name="searxng", raises=True),
        _Runtime(name="ddgs", raises=True),
        _Runtime(name="tavily", raises=True),
    )
    assert mod.SearchTool(Settings()).run({"query": "jarvis"}) == "[]"
