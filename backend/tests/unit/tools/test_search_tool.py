from __future__ import annotations

import json

from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch.base import SearchResult
from backend.app.tools.search import search_tool as mod


class _Runtime:
    def __init__(self, *, raises: bool = False, empty: bool = False) -> None:
        self.raises = raises
        self.empty = empty

    def search(self, query: str, *, max_results: int = 3):
        if self.raises:
            raise RuntimeError("boom")
        if self.empty:
            return []
        return [SearchResult(title="t", url="u", snippet="s", source="src")]


def test_search_tool_returns_json_results_on_success(monkeypatch) -> None:
    captured = {}

    def _selector(settings: Settings):
        captured["called"] = True
        return _Runtime(), object()

    monkeypatch.setattr(mod, "select_search_runtime", _selector)
    out = mod.SearchTool(Settings()).run({"query": "jarvis", "max_results": 1})
    payload = json.loads(out)
    assert captured["called"] is True
    assert payload[0]["title"] == "t"


def test_search_tool_returns_empty_json_when_no_provider(monkeypatch) -> None:
    monkeypatch.setattr(mod, "select_search_runtime", lambda settings: (_Runtime(empty=True), object()))
    assert mod.SearchTool(Settings()).run({"query": "jarvis"}) == "[]"


def test_search_tool_does_not_raise_on_runtime_error(monkeypatch) -> None:
    monkeypatch.setattr(mod, "select_search_runtime", lambda settings: (_Runtime(raises=True), object()))
    assert mod.SearchTool(Settings()).run({"query": "jarvis"}) == "[]"
