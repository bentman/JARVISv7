# New Capability (Concept): Local Tavily-Compatible Search (`tavily-open`)

Status: **concept / not yet slice-planned.** This document preserves research findings and an implementation shape so the idea isn't lost. It is not an implementation plan and authorizes no code changes.

---

## 1. Plain-language summary

Today, JARVISv7's web search tries three things in order: a local search box (SearXNG, if you're running it), a free public search library (DDGS), and paid Tavily search (if you've added an API key). All three mostly return short snippets -- a title, a link, a one-line description.

`tavily-open` is a free, self-hosted tool that does more: it takes those same search results and actually reads the pages, pulling out the real article content instead of just a snippet. It brings its own bundled SearXNG and Redis, so it isn't something we merge into today's stack -- it's a complete alternate stack you run instead of the current one, switched on with a single on/off setting.

---

## 2. Technical definition

### 2.1 What `tavily-open` is

Source: [github.com/jianjungki/tavily-open](https://github.com/jianjungki/tavily-open)

A self-hosted FastAPI service (Uvicorn, default port `8000`) that:
- Takes a search query, runs it against a **bundled SearXNG** instance for result URLs.
- Crawls/extracts full page content for those URLs through a staged fallback chain (direct HTTP fetch -> Jina Reader -> remote Browserless/CDP -> local Playwright).
- Caches results in a **bundled Redis** (`REDIS_URL`, default `redis://localhost:6379/0`).
- Exposes one endpoint: `POST /search`, returning its own schema -- `results: [{content, reference}], success_count, failed_urls, cache_hits, newly_crawled`.

It ships as its own Docker Compose project (API + SearXNG + Redis, same default ports our stack already uses). It has no relationship to `api.tavily.com` and requires no API key.

### 2.2 What it is not

- Not a drop-in replacement for the real Tavily API's request/response schema.
- Does not call `api.tavily.com` under any circumstance.
- Does not ship its own search index -- it depends entirely on its own SearXNG for discovery.
- Not designed to run alongside our current `redis`/`searxng` containers -- default ports collide (`6379`, SearXNG `8080` internal). It's an **alternate** stack, not an addition.

---

## 3. Why it matters -- the gap it closes

| Current runtime | Returns |
|---|---|
| `SearXNGRuntime` | Title + URL + short snippet |
| `DDGSRuntime` | Title + URL + short snippet |
| `TavilyRuntime` (cloud, api-key gated) | Title + URL + extracted content |
| `tavily-open` (proposed) | Reference + extracted page **content**, free, local |

The only runtime today that returns real page content instead of a snippet is the paid cloud Tavily path. `tavily-open` closes that gap locally and at no cost, at the cost of running a second, self-contained Docker stack instead of the current one.

---

## 4. Implementation shape

Single new toggle, single new runtime file, single new docker folder. No changes to the existing four runtimes' code, no new levers beyond the one switch.

### 4.1 `.env` addition

```env
## Alternate search stack (replaces SearXNG/DDGS/Tavily escalation when true)
USE_TAVILYOPEN=false
```

One key. No separate host/port/URL settings -- `TavilyOpenRuntime` targets a fixed local default (`http://127.0.0.1:8000`, tavily-open's own Uvicorn default) since only one search stack is expected to run at a time.

`backend/app/core/settings.py`:
- Add `"USE_TAVILYOPEN": "primary"` to `SETTING_ENV_CLASSIFICATION`, alongside the existing `USE_SEARXNG`/`USE_DDGS`/`USE_TAVILY` entries -- same classification tier, same pattern, no new tier invented.
- Add `use_tavilyopen: bool = field(default_factory=lambda: _env_bool("USE_TAVILYOPEN", False))` to `Settings`, next to `use_tavily`.

### 4.2 New runtime: `backend/app/runtimes/internetsearch/tavilyopen_runtime.py`

Implements the existing `SearchBase` interface exactly like the other three -- no interface change needed:

```python
from __future__ import annotations

import httpx

from backend.app.core.settings import Settings
from backend.app.runtimes.internetsearch.base import SearchBase, SearchResult


class TavilyOpenRuntime(SearchBase):
    def __init__(self, settings: Settings, timeout_s: float = 8.0) -> None:
        self._enabled = bool(settings.use_tavilyopen)
        self._base_url = "http://127.0.0.1:8000"
        self._timeout_s = timeout_s

    def runtime_name(self) -> str:
        return "tavilyopen"

    def is_available(self) -> bool:
        return self._enabled

    def search(self, query: str, *, max_results: int = 5) -> list[SearchResult]:
        if not self._enabled or not query.strip():
            return []
        try:
            response = httpx.post(
                f"{self._base_url}/search",
                json={"query": query, "limit": max(0, max_results)},
                timeout=self._timeout_s,
            )
            response.raise_for_status()
            payload = response.json()
            results = payload.get("results", []) if isinstance(payload, dict) else []
            mapped: list[SearchResult] = []
            for item in results[: max(0, max_results)]:
                if not isinstance(item, dict):
                    continue
                mapped.append(
                    SearchResult(
                        title=str(item.get("reference", "")),
                        url=str(item.get("reference", "")),
                        snippet=str(item.get("content", "")),
                        source="tavilyopen",
                    )
                )
            return mapped
        except Exception:
            return []
```

Field mapping note: `tavily-open`'s schema has no separate `title`; `reference` (the source URL) is used for both `title` and `url` unless/until a cleaner mapping is confirmed against a live instance.

### 4.3 `search_tool.py` wiring

One conditional in `_providers()` -- when the alternate stack is on, it fully replaces the chain rather than joining it, per the "instead of" framing:

```python
def _providers(self) -> list[SearchBase]:
    if self._settings.use_tavilyopen:
        return [TavilyOpenRuntime(self._settings)]
    return [
        SearXNGRuntime(self._settings),
        DDGSRuntime(self._settings),
        TavilyRuntime(self._settings),
    ]
```

No change to `run()`, no change to `SearchResult`, no change to the other three runtime files.

### 4.4 `docker\tavily-open` (new directory)

Clone `jianjungki/tavily-open` as-is into `docker\tavily-open` (new `docker\` root -- doesn't exist today; root `docker-compose.yml` stays where it is, untouched). This becomes a second, independent Compose project:

```text
docker\tavily-open\          <- cloned repo, unmodified
  docker-compose.yml         <- tavily-open's own API + SearXNG + Redis
  .env                       <- tavily-open's own config (CACHE_ENABLED, REDIS_URL, etc.)
  ...
```

Operational model: **run one stack or the other, not both.**

```powershell
# Current stack (default):
docker compose up --detach                        # root docker-compose.yml

# Alternate stack:
docker compose -f docker\tavily-open\docker-compose.yml up --detach
```

```env
# .env
USE_TAVILYOPEN=true
USE_SEARXNG=false
USE_DDGS=false
USE_TAVILY=false
```

Since `tavily-open`'s bundled SearXNG/Redis default to the same ports as ours (`6379`, SearXNG's internal `8080`), starting both stacks at once will port-conflict -- that's expected and reinforces "instead of," not "alongside."

### 4.5 What is deliberately *not* added

- No `TAVILYOPEN_BASE_URL`/`TAVILYOPEN_PORT` setting -- fixed default only, per "keep it simple."
- No merging of `tavily-open`'s bundled Redis with the app's own `REDIS_HOST`/`REDIS_PORT` settings (which also serve episodic-memory caching, not just search) -- the two Redis instances stay conceptually separate; `tavily-open`'s Redis is internal to its own stack and never referenced by `backend/app/core/settings.py`.
- No changes to `SearchResult`, `SearchBase`, or the three existing runtime files.

---

## 5. Open questions (not resolved, for future slice planning)

- Confirm the exact `/search` request/response shape against a live `tavily-open` instance before finalizing `TavilyOpenRuntime` -- the mapping above is from published docs, not a live probe.
- Decide whether `title` should stay mirrored from `reference`, or whether the first line of `content` should be used instead.
- Confirm whether running `docker\tavily-open`'s compose file requires stopping the root stack first (port conflict), or whether remapping ports in one of the two compose files is worth the added complexity -- current recommendation is stop-and-swap, not remap, to keep this a true single-lever toggle.
- Docker resource cost of the `tavily-open` stack (API + its own SearXNG + its own Redis + optional Playwright) vs. the current two-container stack.

---

## References

- `tavily-open` source: https://github.com/jianjungki/tavily-open
- Current repo escalation chain: `backend/app/tools/search/search_tool.py`
- Current repo runtimes: `backend/app/runtimes/internetsearch/`
- Current repo settings/classification: `backend/app/core/settings.py`
