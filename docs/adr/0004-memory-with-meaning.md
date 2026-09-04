# 0004 - Memory with Meaning

Date: 2026-09-01
Status: Implemented
Related: 0002, 0003, 0005, 0006, 0007

## Context and Problem Statement

JARVISv7 needs memory, but not every retained item has the same purpose or authority. Current-turn context, bounded session continuity, event records, durable facts, caches, and audit artifacts need separate ownership and lifecycle rules.

Without layered memory, transcripts, search results, retrieval caches, model-generated summaries, and durable facts can collapse into one ambiguous store that is hard to inspect, correct, forget, or govern.

## Decision Drivers

- Prompt-visible memory must be bounded and labeled as context, not instruction authority.
- Session continuity should preserve useful short-term context without becoming transcript replay.
- Cross-session events need provenance back to committed turn/session artifacts.
- Durable facts need evidence, lifecycle state, revision checks, review, correction, dispute, and forgetting.
- Model-assisted memory extraction must remain proposal-only.
- Caches should accelerate retrieval without becoming memory authority.
- Desktop and API surfaces need to use backend-owned memory services.

## Considered Options

- Replay recent transcripts as the primary memory mechanism.
- Let the model maintain or rewrite durable memory directly.
- Use layered, application-owned memory with explicit promotion and artifact evidence.

## Decision Outcome

Chosen option: `Use layered, application-owned memory with explicit promotion and artifact evidence`.

JARVISv7 implements separate memory layers for present-turn context, active-session working memory, persisted turn/session artifacts, episodic memory, semantic memory, semantic curation jobs, lifecycle controls, and retrieval cache acceleration. Models may propose semantic candidates from persisted evidence, but the application owns durable identity, lifecycle state, correction, deletion, permission, and retention.

## Consequences

Positive:
- The assistant can use memory without treating every transcript, cache entry, or retrieved result as durable truth.
- Durable facts are source-backed, reviewable, correctable, disputable, and forgettable.
- Working, episodic, semantic, artifact, and cache behavior can evolve independently because each layer has a different purpose.
- Desktop and API surfaces share backend-owned memory lifecycle behavior.
- Future tools, skills, MCP, plugins, and agents have one memory ingestion boundary: committed turn/session artifacts.
- Cache and retrieval failures degrade behavior without corrupting memory authority.

Negative:
- Meaningful memory requires more application code than raw transcript replay.
- Review-first semantic memory is slower to become useful than automatic self-editing memory.
- Source artifacts and semantic facts have separate retention and erasure concerns.
- Retrieval ranking, extraction quality, and review ergonomics remain ongoing quality surfaces.
- Future procedural/profile/cross-device memory needs separate architecture rather than being hidden inside semantic facts.

## Implementation

Present-turn context is assembled by the cognition layer. `PromptEnvelope` separates application instructions, personality, continuity, working memory, retrieved memory, search evidence, user input, and output contracts. Retrieved memory is prompt context, not instruction authority.

Working memory is in-process and bounded. `WorkingMemory` keeps recent entries, and `WritePolicy` controls whether responses are added and how many entries are retained. `SessionManager` exposes working context and suppresses it for profile switches or immediate repeats when continuity policy requires it.

Turn and session artifacts are the evidence boundary. `TurnEngine` records transcript, response, prompt, retrieved memory references, search evidence, runtime context, phase timings, failure state, interruptions, raw audio path, and degradation. `TurnArtifact` also defines fields for future action proposals, authorization decisions, approvals, execution results, cancellations, and delegated runs. `SessionArtifact` and `SessionTimeline` preserve session-level evidence.

Episodic memory is local JSON under `data/memory/episodic/`. It writes eligible successful turn artifacts, retains a bounded number of sessions, retrieves recent or keyword-matched entries, and tolerates storage failures without breaking the turn.

Semantic memory is local SQLite under `data/memory/semantic/memory.sqlite`. The schema stores governed facts, evidence records, lifecycle events, curation policy, curation jobs, and content revision. Retrieval uses active lifecycle state, source evidence, lexical/vector search, and stable cache identity.

Semantic curation is opt-in and review-first. Closed sessions can enqueue durable curation jobs only when policy authorizes them. The background worker uses the shared LLM execution coordinator so interactive work wins over curation. Extraction asks the model for small JSON proposals from persisted turn transcripts. The application verifies exact evidence excerpts, derives provisional claim identity, persists pending-review candidates, and requires user or application lifecycle actions before records become trusted durable facts.

Memory lifecycle is service-owned. `/memory` exposes policy, bounded list/detail, confirm, correct, dispute, forget, and curation status with revision checks. Forgetting stops use of the governed semantic record; source turn and session artifacts are separate evidence stores.

Desktop memory controls call backend/Tauri memory APIs. `desktop/src/components/memory-panel.js` inspects memory and requests lifecycle actions through backend policy. `desktop/src/api-client.js` centralizes the frontend memory API calls, and `desktop/src-tauri/src/backend.rs` bridges those calls to backend routes.

Redis-backed retrieval caching is acceleration only. Cache keys include backend availability and content revision where needed, and cache failure falls back to direct retrieval or no retrieved context.

## Confirmation

Implementation files:
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

Test coverage:
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

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration` when curation or lifecycle integration changes
- `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families services,turn --devices ...` for live Redis or turn-continuity validation claims
- `npm --prefix desktop test` for desktop memory contract changes

## Follow-up

None for this ADR.

Future procedural memory, explicit profile memory, cross-device memory, physical artifact erasure, or tool/agent memory evidence should update this ADR when they preserve this layered memory architecture, or create/supersede an ADR when they change it.
