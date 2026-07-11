# New Capability (Concept): Local Tavily-Compatible Search (`tavily-open`)

Status: **concept / not yet slice-planned.** This document preserves research findings and architectural direction so the idea isn't lost. It is not an implementation plan and authorizes no code changes.

---

## 1. Plain-language summary

Today, JARVISv7's web search tries three things in order: a local search box (SearXNG, if you're running it), a free public search library (DDGS), and paid Tavily search (if you've added an API key). All three mostly return short snippets -- a title, a link, a one-line description.

`tavily-open` is a free, self-hosted tool that does more: it takes those same search results and actually reads the pages, pulling out the real article content instead of just a snippet. That's the same thing the *paid* Tavily service is normally used for -- but running locally, for free, using search infrastructure we already have installed (SearXNG + Redis).

The idea is not to replace anything that works today. It's to add a "get the real content, not just the snippet" step, using tools we already run, before falling back to the existing snippet-only or paid options.

---

## 2. Technical definition

### 2.1 What `tavily-open` is

Source: [github.com/jianjungki/tavily-open](https://github.com/jianjungki/tavily-open)

A self-hosted FastAPI service that:
- Takes a search query, runs it against a **SearXNG** instance for result URLs.
- Crawls/extracts full page content for those URLs through a staged fallback chain (direct HTTP fetch -> Jina Reader -> remote Browserless/CDP -> local Playwright).
- Optionally caches results in **Redis**.
- Exposes one endpoint: `POST /search`, returning its own schema -- `results: [{content, reference}], success_count, failed_urls, cache_hits, newly_crawled`.

It requires SearXNG to expose `formats: [html, json]`. It has no relationship to `api.tavily.com` and requires no API key -- despite the name, it is an independent local alternative, not a proxy or fallback wrapper for the real Tavily cloud API.

### 2.2 What it is not

- It is **not** a drop-in replacement for the real Tavily API's request/response schema.
- It does **not** call `api.tavily.com` under any circumstance.
- It does **not** ship its own search index -- it depends entirely on SearXNG for discovery; its value-add is the content-extraction layer on top.

---

## 3. Why it matters -- the actual gap it closes

| Current runtime | Returns |
|---|---|
| `SearXNGRuntime` | Title + URL + short snippet |
| `DDGSRuntime` | Title + URL + short snippet |
| `TavilyRuntime` (cloud, api-key gated) | Title + URL + extracted content |
| `tavily-open` (proposed) | Reference + extracted page **content**, free, local |

The only runtime today that returns real page content instead of a snippet is the paid cloud Tavily path, which requires an API key. `tavily-open` would close that gap locally and at no cost, using infrastructure already provisioned.

---

## 4. Correlation to current codebase (as inspected)

| Repo surface | Current state | Relevance |
|---|---|---|
| `backend/app/tools/search/search_tool.py` | Escalates `SearXNGRuntime -> DDGSRuntime -> TavilyRuntime`, all implementing `SearchBase` | New runtime would slot in as a fourth implementation of the same interface |
| `backend/app/runtimes/internetsearch/base.py` | `SearchBase(runtime_name, is_available, search)`, `SearchResult(title, url, snippet, source)` | Stable interface; a `tavily-open` runtime maps cleanly onto it (`content` -> `snippet`/new field) |
| `backend/app/runtimes/internetsearch/searxng_runtime.py` | Local-only, gated by `USE_SEARXNG`, no public-instance fallback | `tavily-open` would call this same local SearXNG, not a second instance |
| `backend/app/runtimes/internetsearch/tavily_runtime.py` | Calls `api.tavily.com` directly, gated by `USE_TAVILY` + `TAVILY_API_KEY` | Distinct from `tavily-open`; candidate to become mode-aware (`local` vs `cloud`) rather than adding a fully separate class |
| `docker-compose.yml` | `redis` + `searxng` services; `searxng` already `depends_on: redis` | A `tavily-open` service should point at these existing containers, not start its own SearXNG/Redis |
| `config/search/searxng/settings.yml` | Already sets `formats: [html, json]` | Already satisfies `tavily-open`'s SearXNG requirement -- no config change needed there |
| `config/search/tavily/` | Exists, empty (`.gitkeep` only) | Already-reserved config surface for this exact purpose -- no new root needed |
| `config/search/ddgs/` | Exists, empty (`.gitkeep` only) | Unrelated placeholder, noted for completeness |

**Conclusion: no new architectural surface is required.** Every piece this concept needs (interface, config directory, container dependency chain, JSON-format SearXNG) already exists in reserved or active form.

---

## 5. Proposed integration shape (conceptual -- not scoped/sequenced)

- Prefer **modifying `TavilyRuntime`** into a mode-aware runtime (`TAVILY_MODE=local|cloud`, mirroring the repo's existing local/managed-vs-cloud pattern such as `LLM_MODEL_MODE`) over adding a wholly separate class -- one setting, one class, two backends.
- Add a `tavily-open` service to `docker-compose.yml`, configured to use the existing `redis`/`searxng` containers rather than duplicating them.
- Use the already-reserved `config/search/tavily/` directory for its config, rather than a new root.
- Likely escalation position: after `SearXNGRuntime` (cheap/fast snippet pass) and before `DDGSRuntime`/cloud fallback -- i.e., "get real content" as the second-tier attempt, not the first or last.

---

## 6. Open questions (not resolved, for future slice planning)

- Does `tavily-open`'s response schema map cleanly enough onto `SearchResult(title, url, snippet, source)`, or does it need a distinct field (e.g. `content`) surfaced to the LLM differently than a snippet?
- Should `USE_SEARXNG=false` (SearXNG container absent) hard-disable `tavily-open` too, since it depends on SearXNG? (Current evidence says yes -- no independent search capability of its own.)
- Docker resource cost of adding a fourth container (`tavily-open` itself, beyond `redis`/`searxng`) -- acceptable for an optional service, but worth noting in provisioning docs.
- Whether the Playwright-based crawl fallback introduces a browser-automation dependency the repo doesn't currently carry, and what that means for provisioning/footprint.

---

## References

- `tavily-open` source: https://github.com/jianjungki/tavily-open
- Current repo escalation chain: `backend/app/tools/search/search_tool.py`
- Current repo runtimes: `backend/app/runtimes/internetsearch/`
