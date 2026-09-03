# 0004 - Memory with Meaning

## Status

Accepted, living.

## Context

JARVISv7 remembers through separate layers with separate owners. Some context exists to finish the current turn. Some state keeps a session coherent. Some records preserve what happened. Some facts become useful across sessions after evidence and review.

The fourth project promise is memory with meaning: every retained item needs a clear purpose, authority, storage owner, retrieval path, and correction or forgetting path.

Current assistant and agent systems follow the same broad split. OpenAI Agents sessions preserve conversation items behind a session interface. LangGraph separates short-term thread state from long-term namespaced stores. Letta/MemGPT-style systems structure durable context into bounded memory blocks and background updates. JARVISv7 uses the same layering and bounded-context discipline while keeping durable memory local, evidence-backed, review-first, and application-owned.

## Decision

JARVISv7 uses layered memory with explicit promotion between layers.

The implemented memory layers are:

1. present-turn context: request, prompt envelope, runtime state, tool/search/retrieval evidence, and intermediate results
2. active-session working memory: bounded recent response context for continuity
3. episodic memory: selected turn events across sessions with source turn/session provenance
4. semantic memory: governed durable facts with evidence, lifecycle state, revision, and review controls
5. artifacts and audit evidence: durable proof of what happened, retrievable deliberately but not automatically promoted

The defined next layers are:

1. procedural memory: reusable ways to work, preferably as skills or other bounded extension artifacts
2. profile/configuration state: explicit preferences, permissions, voice choices, defaults, and personality settings
3. richer audit records for tools, agents, approvals, and delegated work
4. cross-device or decentralized memory sync
5. physical erasure policy for source artifacts beyond semantic forgetting

Only the application promotes memory. Models may propose semantic candidates from persisted evidence. They do not own durable identity, lifecycle state, correction, deletion, permission, or retention.

All implemented interaction surfaces feed memory through the same committed turn/session artifact path. Future daemon and TUI clients must use that same path.

Search results, retrieved context, Redis, and other caches provide recall acceleration and prompt context. Governed memory stores remain the authority for durable memory.

## Current Design

Present-turn context is assembled by the cognition layer. `PromptEnvelope` separates application instructions, personality, continuity, working memory, retrieved memory, search evidence, user input, and output contracts. Retrieved memory is prompt context, not instruction authority.

Working memory is in-process and bounded. `WorkingMemory` keeps recent entries, and `WritePolicy` controls whether responses are added and how many entries are retained. `SessionManager` exposes working context and suppresses it for profile switches or immediate repeats when continuity policy requires it.

Turn and session artifacts are the evidence boundary. `TurnEngine` records transcript, response, prompt, retrieved memory references, search evidence, runtime context, phase timings, failure state, interruptions, raw audio path, and degradation. `SessionManager` records ordered timeline events and writes turn/session artifacts.

Episodic memory is local JSON under `data/memory/episodic/`. It writes eligible successful turn artifacts, retains a bounded number of sessions, retrieves recent or keyword-matched entries, and tolerates storage failures without breaking the turn.

Semantic memory is local SQLite under `data/memory/semantic/memory.sqlite`. The schema stores governed facts, evidence records, lifecycle events, curation policy, curation jobs, and content revision. Retrieval uses active lifecycle state, source evidence, lexical/vector search, and stable cache identity.

Semantic curation is opt-in and review-first. Closed sessions can enqueue durable curation jobs only when policy authorizes them. The background worker uses the shared LLM execution coordinator so interactive work wins over curation. Extraction asks the model for small JSON proposals from persisted turn transcripts. The application verifies exact evidence excerpts, derives provisional claim identity, persists pending-review candidates, and requires user or application lifecycle actions before records become trusted durable facts.

Memory lifecycle is service-owned. `/memory` exposes policy, bounded list/detail, confirm, correct, dispute, forget, and curation status with revision checks. Forgetting stops use of the governed semantic record; source turn and session artifacts are separate evidence stores.

Desktop memory controls call backend/Tauri memory APIs. The desktop surface inspects memory and requests lifecycle actions through backend policy.

Redis-backed retrieval caching is acceleration only. Cache keys include backend availability and content revision where needed, and cache failure falls back to direct retrieval or no retrieved context.

## Memory Layers

Implemented now:

- present-turn context
- active-session working memory
- persisted turn/session artifacts
- episodic memory
- governed semantic memory
- semantic curation jobs
- backend and desktop semantic lifecycle controls
- retrieval cache acceleration

Defined next:

- procedural memory as skills or equivalent extension artifacts
- explicit user/assistant profile memory separate from ordinary semantic facts
- richer audit records for tools, agents, approvals, and delegated work
- cross-device or decentralized memory sync
- physical erasure policy for source artifacts beyond semantic forgetting

## Consequences

Benefits:

- The assistant can use memory without treating every transcript, cache entry, or retrieved result as durable truth.
- Durable facts are source-backed, reviewable, correctable, disputable, and forgettable.
- Working, episodic, and semantic recall can evolve independently because each layer has a different purpose.
- Future daemon, TUI, tool, skill, and agent work has one memory ingestion boundary: committed turn/session artifacts.
- Cache and retrieval failures degrade behavior without corrupting memory authority.

Costs:

- Meaningful memory takes more application code than raw transcript replay.
- Review-first semantic memory is slower to become useful than automatic self-editing memory.
- Source artifacts and semantic facts require separate retention and erasure policies.
- Retrieval ranking, extraction quality, and user review ergonomics need continued tuning.
- Profile and procedural memory still need explicit design before they can be treated as implemented layers.

## Remaining Work

- Define procedural memory through skills or another bounded extension contract.
- Define explicit user and assistant profile state for preferences, defaults, voice/personality choices, permissions, and stable interaction settings.
- Improve live-model extraction quality, rejection reporting, and review ergonomics without giving the model lifecycle authority.
- Tighten retrieval ranking, freshness, source attribution, and prompt formatting for mixed episodic and semantic context.
- Define retention and physical-erasure policy for turn/session artifacts separately from semantic forgetting.
- Make future daemon and TUI clients use the same memory APIs and artifact path as desktop.
- Extend artifacts to capture tool, approval, skill, MCP, plugin, and agent memory evidence when those promises are implemented.
- Decide whether any durable shared-memory or cross-device sync layer belongs in this personal-project scope.

## Implementation Path

Make memory changes inside the existing memory and artifact ownership model:

1. Add or adjust prompt-visible context through `backend/app/cognition/prompt_assembler.py` and retrieval helpers.
2. Keep working, episodic, semantic, retrieval, curation, and lifecycle behavior in `backend/app/memory/`.
3. Expose operator actions through `backend/app/services/memory_service.py` and `backend/app/api/routes/memory.py`.
4. Preserve turn/session evidence in `backend/app/artifacts/` before promoting durable semantic facts.
5. Update desktop memory inspection through `desktop/src/components/memory-panel.js` and backend/Tauri APIs only after backend contracts exist.
6. Add focused tests under `backend/tests/unit/memory/`, `backend/tests/unit/services/`, `backend/tests/unit/api/`, and existing runtime cache tests when Redis behavior changes.

Dependencies: memory changes depend on prompt assembly, turn/session artifacts, memory storage modules, curation services, lifecycle APIs, and desktop inspection contracts.

Targets: `backend/app/memory/`, memory services and routes, artifact schemas, prompt assembly, retrieval cache tests, and desktop memory components.

Exit evidence: unit tests for changed memory layer behavior, service/API tests for lifecycle changes, artifact assertions for promotion evidence, and live Redis/runtime tests only when cache behavior changes.

## Guidance

When adding memory behavior:

1. Name the memory layer and purpose before choosing storage.
2. Define the authority that may create, promote, retrieve, update, and forget it.
3. Keep prompt-visible memory bounded and labeled as context.
4. Use persisted turn/session artifacts as the normal evidence boundary.
5. Require exact evidence, revision checks, and lifecycle events for durable semantic facts.
6. Treat caches as rebuildable acceleration.
7. Route desktop, CLI/script, future daemon, and future TUI memory actions through backend services.

When adding model-assisted memory:

1. Ask the model only for bounded proposals.
2. Parse with a strict schema and reject excess fields, excess length, duplicates, and unsupported evidence.
3. Verify candidate evidence against persisted artifacts.
4. Keep identity, lifecycle state, confidence, importance, correction, dispute, and forgetting application-owned.
5. Persist uncertain durable memory as review-required records.

When adding tools, skills, MCP, plugins, or agents:

1. Record the action and result in the same turn/session artifact model.
2. Promote durable memory only through the governed memory service.
3. Scope memory visibility by role, authorization, session, and evidence policy.
4. Keep profile and procedural state explicit in their owning extension or configuration layer.

## Evidence

Implementation:

- `backend/app/cognition/prompt_envelope.py`
- `backend/app/cognition/prompt_assembler.py`
- `backend/app/cognition/memory_extraction.py`
- `backend/app/conversation/engine.py`
- `backend/app/conversation/session_manager.py`
- `backend/app/artifacts/turn_artifact.py`
- `backend/app/artifacts/session_artifact.py`
- `backend/app/artifacts/session_timeline.py`
- `backend/app/memory/working.py`
- `backend/app/memory/write_policy.py`
- `backend/app/memory/episodic.py`
- `backend/app/memory/retrieval.py`
- `backend/app/memory/semantic.py`
- `backend/app/memory/curation.py`
- `backend/app/memory/curation_contract.py`
- `backend/app/memory/curation_reconciliation.py`
- `backend/app/services/memory_curation_service.py`
- `backend/app/services/memory_curation_processor.py`
- `backend/app/services/memory_service.py`
- `backend/app/services/llm_execution_coordinator.py`
- `backend/app/api/routes/memory.py`
- `backend/app/api/routes/memory_curation.py`
- `backend/app/api/schemas/memory.py`
- `desktop/src/components/memory-panel.js`
- `desktop/src/api-client.js`
- `desktop/src-tauri/src/backend.rs`

Tests:

- `backend/tests/unit/memory/test_working_memory.py`
- `backend/tests/unit/memory/test_episodic.py`
- `backend/tests/unit/memory/test_retrieval.py`
- `backend/tests/unit/memory/test_semantic.py`
- `backend/tests/unit/memory/test_semantic_lifecycle.py`
- `backend/tests/unit/memory/test_curation_contract.py`
- `backend/tests/unit/memory/test_curation_reconciliation.py`
- `backend/tests/unit/memory/test_curation_jobs.py`
- `backend/tests/unit/cognition/test_memory_extraction.py`
- `backend/tests/unit/cognition/test_prompt_assembler.py`
- `backend/tests/unit/conversation/test_engine.py`
- `backend/tests/unit/conversation/test_session_manager.py`
- `backend/tests/unit/services/test_memory_curation_service.py`
- `backend/tests/unit/services/test_memory_curation_processor.py`
- `backend/tests/unit/services/test_memory_service.py`
- `backend/tests/unit/services/test_llm_execution_coordinator.py`
- `backend/tests/unit/api/test_memory_routes.py`
- `backend/tests/unit/api/test_memory_curation_routes.py`
- `backend/tests/integration/test_memory_curation_review_pipeline.py`
- `backend/tests/runtime/services/test_redis_retrieval_cache_live.py`
- `backend/tests/runtime/turn/test_continuity_retrieval_live.py`

External practice reviewed:

- OpenAI Agents SDK: [Sessions](https://openai.github.io/openai-agents-js/guides/sessions/) and custom session storage.
- LangGraph: [short-term and long-term memory concepts](https://github.com/langchain-ai/langgraphjs/blob/main/docs/docs/concepts/memory.md).
- Letta/MemGPT lineage: [memory blocks and context management](https://www.letta.com/blog/memory-blocks/).
