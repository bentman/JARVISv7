# Internet Search Capability Correction (Architectural Outline)

Status: **proposal / not yet slice-planned.** This document defines the narrow architectural shape for connecting the existing internet-search runtimes to the normal JARVIS turn path. It is not completion evidence and authorizes no code changes.

---

## 1. Plain-language summary

JARVISv7 already contains three working search adapters: SearXNG, DDGS, and Tavily. They can be called directly, but the assistant cannot use them during a normal text or voice conversation. That is the gap this correction closes.

The intended behavior is simple:

1. A normal turn reaches the existing reasoning path.
2. Reasoning explicitly decides whether current internet information is needed.
3. If search is requested, the application calls one search service.
4. That service tries the enabled providers in the existing order.
5. Returned results are treated as untrusted external context.
6. JARVIS answers from those results and returns the source URLs.
7. If no provider can serve the request, JARVIS says that live information could not be verified.

Text and voice remain two entrances to the same turn engine. Search does not become a separate endpoint, agent, workflow, or desktop feature family.

---

## 2. Observed repository baseline

The required foundation is already present:

- `backend/app/runtimes/internetsearch/` contains `SearXNGRuntime`, `DDGSRuntime`, and `TavilyRuntime` behind the shared `SearchBase` interface.
- `backend/app/core/settings.py` already owns the provider enablement settings and Tavily credential.
- `backend/app/api/app.py` already composes runtime and application services through `ApiState`.
- `backend/app/conversation/engine.py` is the shared cognition path for text and voice turns.
- `ConversationState.ACTING` already exists between `REASONING` and `RESPONDING` but is not currently used by normal turns.
- `PromptEnvelope` already supports an untrusted `tool_result` content type.
- `TurnArtifact` already provides `tools_invoked`, `reasoning_trace_metadata`, and `runtime_context` evidence fields.
- `/task/text` and `/session/ptt` are the normal text and resident-voice product entrances.
- The desktop already consumes the answer text from those API paths and already understands the `ACTING` turn state.

The current inventory accurately records the limitation: the providers are runtime substrate and have no normal conversation invocation path.

This correction should connect those existing pieces. It should not replace them with a broader capability framework.

---

## 3. Architectural boundaries

The correction follows the project vision's existing division of responsibility:

- The **model interprets and proposes** whether live search is needed.
- The **application validates the proposal**, selects the action path, controls provider execution, bounds results, and owns failure behavior.
- The **search service coordinates providers** but does not decide conversational intent.
- The **provider runtimes perform provider-specific I/O** and retain their current settings boundaries.
- The **prompt envelope carries results as untrusted context** rather than converting provider text into instructions.
- The **turn artifact records what was decided and attempted**.

Provider enablement is the existing operator boundary. A turn may use only providers enabled by settings; model output cannot enable a provider, supply a credential, select an arbitrary endpoint, or bypass the configured provider order.

Internet search is a remote, read-only action. This correction does not grant write authority or introduce general-purpose tool execution.

---

## 4. Turn-flow correction

### 4.1 Reasoning decision

The first model response for a turn has two valid outcomes:

```text
respond with the answer

or

request internet search with a bounded query
```

The exact wire representation should be deliberately small. A practical shape is a reserved search directive, for example:

```text
SEARCH: <query>
```

Any response that does not match the directive is the ordinary assistant answer. This preserves the existing one-model-call path for turns that do not search. A search turn performs a second model call only after results exist.

The application parses the directive into an explicit decision record:

```text
SearchDecision
  requested: true | false
  query: bounded string | null
  reason: explicit-search-decision | ordinary-response
```

The model proposes the query. The application trims it, rejects an empty query, applies a fixed maximum length, and never interprets it as an endpoint or command.

### 4.2 Acting

When `requested` is true, the existing turn context advances:

```text
REASONING -> ACTING
```

`TurnEngine` calls the injected internet-search service. The service tries enabled providers in this order:

1. SearXNG
2. DDGS
3. Tavily

The first provider returning usable results wins. Empty or failed attempts fall through to the next enabled provider. The service returns one bounded outcome rather than exposing provider-selection policy to `TurnEngine`.

Suggested service result shape:

```text
SearchOutcome
  status: completed | unavailable
  provider: searxng | ddgs | tavily | null
  results: bounded SearchResult list
  attempted_providers: ordered provider-name list
  reason: concise application-safe explanation
```

The existing provider adapters may continue to fail closed by returning no results. The service owns the distinction visible to the turn: at least one provider returned usable results, or no enabled provider could provide usable results. This correction does not require redesigning every adapter's error contract.

### 4.3 Responding with results

Successful results are added to the final `PromptEnvelope` as one untrusted segment:

```text
authority: tool
content_type: tool_result
trusted: false
```

The segment contains only bounded fields already represented by `SearchResult`:

- title
- URL
- snippet
- provider source

The application limits result count and field lengths before prompt assembly. Result text is context, never instruction authority.

The final trusted output contract tells the model to:

- answer the user's original request using relevant returned information;
- cite only URLs present in the supplied results;
- avoid inventing source URLs or claiming broader browsing;
- distinguish uncertainty when the results do not support a firm answer.

The turn then follows the existing response path:

```text
ACTING -> RESPONDING -> IDLE
```

For voice, the same answer body continues through the existing TTS path.

### 4.4 Unavailable search

If search was requested but no provider is enabled, or all enabled providers return no usable result, the application does not pass fabricated search context to the model.

It returns a concise degraded answer such as:

```text
I couldn't verify that with live search because no configured search provider returned results.
```

The turn itself remains recoverable; unavailable search is not a backend crash. The outcome records `status=unavailable`, the attempted providers, and the reason.

This behavior must be identical whether the request entered through text or voice.

---

## 5. Answer and source contract

Search provenance belongs with the turn result, not only inside generated prose.

Suggested result shape:

```text
TurnSearchSummary
  requested: boolean
  status: not_requested | completed | unavailable
  provider: string | null
  sources: [{title, url, provider}]
  reason: string | null
```

`TurnResult` carries this summary. The existing task response and session status map the same shape so text and voice expose the same evidence.

For the existing desktop conversation surface, the answer remains the normal message body. A small source footer may be appended to the displayed response text so the current surface receives the URLs without a separate search interface. The TTS input should remain the answer body and should not read the source footer aloud.

This keeps source handling narrow:

- no search-results page;
- no search history panel;
- no independent citation store;
- no desktop provider selector;
- no new API route.

---

## 6. Composition and evidence

### 6.1 Application composition

One `InternetSearchService` is created during normal application startup and stored in `ApiState`.

`build_engine()` passes the same service into every `TurnEngine`, including engines created when a new session starts. This prevents the initial engine, replacement session engines, and resident voice engine from drifting into different search behavior.

Directly constructed test engines may receive an unavailable/null service so existing non-search tests remain explicit and deterministic.

### 6.2 Turn artifact

The existing artifact fields are sufficient:

- `reasoning_trace_metadata` records the search decision and bounded query metadata.
- `tools_invoked` records the selected search capability/provider when a provider is called.
- `runtime_context` records the outcome, attempted providers, degraded reason, and returned source URLs.
- `final_prompt_text` shows that results entered the model context under the untrusted tool-result header.

No second search ledger or parallel artifact format is needed.

### 6.3 Session status

The session service retains the latest `TurnSearchSummary` alongside the existing last transcript and response. `/session/status` therefore exposes the completed voice-turn sources and degraded state without reaching into logs or reconstructing behavior from prompt text.

---

## 7. Placement outline

| Area | Intended adjustment |
|---|---|
| `backend/app/services/` | Add the single provider-selecting internet-search service. |
| `backend/app/cognition/` | Define/parse the bounded search directive and assemble untrusted results. |
| `backend/app/conversation/engine.py` | Add the explicit decision and `ACTING` branch to the shared reasoning path. |
| `backend/app/api/app.py` | Construct and inject the service through `ApiState` and session engine creation. |
| Existing task/session schemas and routes | Return the common search summary with text and voice results. |
| `backend/app/services/session_service.py` | Preserve the latest voice-turn search summary in session status. |
| Existing turn artifacts | Populate existing evidence fields; do not add a parallel artifact. |
| Existing unit/integration tests | Prove decision, provider selection, prompt trust, sources, and degradation. |

`repo_tree.md` already places provider runtimes under `runtimes/`, coordination under `services/`, cognition under `cognition/`, and turn flow under `conversation/`. This correction does not change repository shape.

---

## 8. Proof contract

Direct runtime tests remain supporting evidence only. Completion evidence must begin at the normal API surfaces.

### Text path

```text
POST /task/text
  -> normal TurnEngine reasoning
  -> explicit SEARCH decision
  -> ACTING
  -> configured provider called
  -> untrusted results in final PromptEnvelope
  -> answer uses a returned fact
  -> response includes the returned source URL
```

### Voice path

```text
POST /session/ptt
  -> resident voice capture/STT
  -> the same TurnEngine reasoning path
  -> the same search service and provider selection
  -> answer spoken through the existing TTS path
  -> /session/status returns the same search summary and source URL
```

### Degraded path

```text
search decision requested
  -> no enabled provider, or no provider returns usable results
  -> no untrusted result segment is fabricated
  -> recoverable unavailable response
  -> task/session result and artifact report the reason
```

Required behavior coverage should verify:

- ordinary non-search turns remain on `REASONING -> RESPONDING`;
- search turns use `REASONING -> ACTING -> RESPONDING`;
- provider order and fallback are deterministic;
- result count and field sizes are bounded;
- the tool-result segment is untrusted in flat and chat prompt rendering;
- answer sources are limited to returned provider URLs;
- unavailable search is visible and does not fail the session;
- text and voice use the same service instance and orchestration path;
- conversation, voice, memory, personality, interruption, and desktop behavior remain unchanged outside the search branch.

---

## 9. What is deliberately not included

- No agent architecture or agent-specific search route.
- No general tool registry, plugin system, permission framework, planner, or autonomous loop.
- No separate search API for users to call directly.
- No replacement of the existing SearXNG, DDGS, or Tavily runtimes.
- No new provider settings, dependencies, storage roots, or Docker services.
- No arbitrary URL fetching or page-crawling capability.
- No search-result persistence outside the existing turn/session artifact path.
- No redesign of global readiness or service-health reporting.
- No desktop search workspace, provider selector, or search-history UI.
- No claim that tests calling providers directly prove the product capability.

---

## 10. Open questions for slice planning

- Confirm the exact reserved decision syntax that the active local LLM follows reliably without affecting ordinary answers. `SEARCH: <query>` is the current smallest candidate.
- Choose the fixed query, result-count, title, snippet, and URL bounds using the active model context limits.
- Decide whether an empty result from a provider is reported simply as "no usable results" or whether the existing runtime adapters need a later, separate error-detail improvement.
- Confirm whether source URLs should appear only in the structured API summary or also as a plain-text footer in `response_text`. The footer is the smallest way to keep the current desktop useful without adding a UI feature.
- Define the exact live product-path validation setup for `/session/ptt` so the proof exercises resident voice orchestration rather than calling `TurnEngine.run_voice_turn()` directly.

---

## References

- Repository operating contract: `AGENTS.md`
- Product architecture and growth order: `ProjectVision.md`
- Current capability ledger: `SYSTEM_INVENTORY.md`
- Repository placement guide: `repo_tree.md`
- Existing search runtimes: `backend/app/runtimes/internetsearch/`
- Shared turn path: `backend/app/conversation/engine.py`
- Prompt trust boundary: `backend/app/cognition/prompt_envelope.py`
- Turn evidence model: `backend/app/artifacts/turn_artifact.py`
