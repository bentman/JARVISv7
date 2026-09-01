# 0003 - Mind with Boundaries

## Status

Accepted, living.

## Context

JARVISv7 uses models for interpretation, synthesis, classification, extraction, and proposals. The application owns state, permissions, retries, interruption, approvals, actions, handoffs, artifacts, memory lifecycle, and failure recovery.

The third project promise is a mind with boundaries: model behavior is useful and expressive while remaining inspectable, bounded, and subordinate to application-owned contracts.

Current assistant and agent systems follow the same broad pattern. Model calls are wrapped by application code that owns instructions, tools, guardrails, state, tracing, handoffs, and human approval. Provider and protocol contracts expose model capability for application policy to compose.

## Decision

JARVISv7 treats the model as a worker inside the assistant.

The application owns:

1. session and turn state
2. prompt assembly and authority labels
3. personality compilation and forbidden override rules
4. provider selection, fallback, and cloud-escalation policy
5. search planning, private-data checks, grounding, and cancellation
6. memory proposal parsing, evidence verification, lifecycle, and review
7. runtime readiness, diagnostics, and degraded state
8. artifacts, audit evidence, and status reporting

The model may produce natural-language responses, structured classifications, search plans, memory candidates, and later tool or agent proposals. Those outputs become trusted only after application-owned parsing, validation, authorization, or operator review.

This ADR defines the model/application boundary for later tools, skills, MCP, plugins, and agents: the model proposes or requests; the application decides and records.

## Current Design

Prompt construction uses explicit authority. `PromptEnvelope` stores segments with `authority`, `content_type`, and `trusted` flags. `assemble_prompt_envelope()` separates application rules, personality style, session continuity, working memory, retrieved context, user input, and output contract. Renderers preserve those boundaries for provider-specific calls.

Personality owns style. `compile_personality_policy()` turns a profile into response guidance and examples, while safety, tool, routing, memory, and factual-grounding policy remain application-owned.

Conversation state is deterministic. `ConversationState` and `TurnContext.advance()` define legal transitions, interruption behavior, recovery state, session closure, and final artifact shape.

Provider routing is application-owned. `RoutedLLM` selects primary, fallback, or cloud profile according to saved selection and explicit user request. It classifies provider failures before fallback and records attempt evidence. Provider adapters serialize prompt envelopes into each provider protocol.

Search uses a bounded planning boundary. `SearchIntentResolver` treats model output as a strict `SearchPlan`, rejects secrets, asks for confirmation before private outbound queries, limits query count, and sends only public-topic queries to search providers. `ground_search_prompt()` treats web evidence as untrusted tool context and requires cited, bounded synthesis.

Memory extraction is proposal-only. `MemoryCandidateExtractor` asks the model for bounded JSON candidates from persisted turn fields. `parse_model_proposals()` strictly parses the shape. `verify_evidence_refs()` checks source turn, source field, and exact excerpt. `build_provisional_candidate()` creates review-only candidates, and application-owned identity/lifecycle decisions create governed facts.

Memory lifecycle is service-owned. `/memory` routes expose policy, inspection, confirmation, correction, dispute, and forgetting through `MemoryService`.

LLM execution is coordinated. `LLMExecutionCoordinator` gives interactive work priority over background curation and blocks new interactive work during shutdown drain.

The backend/daemon boundary reinforces these rules. Desktop, CLI/script, and future TUI clients call backend APIs for cognition, memory, state transitions, and approval semantics.

## Boundaries

Current implemented boundaries:

- Application and personality instructions are separated from user, memory, retrieval, and tool context.
- Memory and retrieval are untrusted context, not instructions.
- User input is instruction only at user authority, not application authority.
- State transitions are deterministic application behavior.
- Search plans are structured, bounded, cancellable, and privacy-gated.
- Provider selection and fallback are deterministic application behavior.
- Semantic memory candidates require persisted evidence and review-first lifecycle.
- Desktop memory controls call backend-owned lifecycle APIs.

Next boundaries:

- Tool execution uses one capability registry and one authorization path.
- Mutating tools require explicit operator approval before execution.
- MCP/server-declared metadata is recorded as claims.
- Skills are procedural guidance or bounded executors with explicit provenance.
- Agents are role-scoped workers governed by the same turn, policy, memory, tool, and artifact boundaries.

## Consequences

Benefits:

- Prompts can include useful context without giving that context policy authority.
- Personality can vary style without changing safety, routing, memory, or action rules.
- Model-proposed memory cannot silently become durable truth.
- Provider differences are hidden behind adapter contracts while product policy stays local.
- Search and retrieval evidence can improve answers without becoming instructions.
- Future tools, skills, MCP, plugins, and agents have a clear boundary to attach to.

Costs:

- More behavior must pass through typed contracts, parsers, services, and status surfaces.
- Some useful model autonomy is intentionally delayed until authorization and evidence paths exist.
- Provider-native features cannot be used directly when they bypass application policy.
- The boundary adds friction for quick experiments, especially around tools and agents.

## Remaining Work

- Define one authorization context for cloud use, mutating tools, workspace writes, privileged agent execution, and external side effects.
- Define a capability registry that unifies built-in tools, search, skills, MCP tools, plugins, and agent delegation without name or permission ambiguity.
- Add explicit approval and audit records for side effects.
- Make provider-native tool calling pass through application-owned capability schemas, permission classes, and result recording.
- Treat MCP discovery as contract capture. Server annotations may inform UI; application policy grants permission.
- Define skill provenance and execution boundaries before skills become model-callable.
- Define agent profiles, delegation, handoff, process authority, memory scope, and completion contracts before agents can act beyond ordinary turns.
- Extend turn artifacts to record tool/action proposals, approvals, denials, execution results, and delegated agent runs as those features land.
- Keep future TUI and daemon clients on backend APIs for approvals, tools, memory, and state.

## Implementation Path

Make model-facing changes by placing the boundary before side effects:

1. Add prompt or output contracts in `backend/app/cognition/`.
2. Keep provider protocol conversion in `backend/app/runtimes/llm/` and routing policy in `backend/app/routing/` or `backend/app/services/`.
3. Parse and validate model output before it reaches memory, search, tools, settings, files, providers, or agents.
4. Store accepted evidence in `backend/app/artifacts/` and use backend services for durable state changes.
5. Add focused tests under `backend/tests/unit/cognition/`, `backend/tests/unit/routing/`, `backend/tests/unit/runtimes/llm/`, and the affected service/API test directory.

Dependencies: model-facing changes depend on prompt envelopes, provider adapters, routing policy, parser/schema boundaries, backend services, and artifact recording.

Targets: cognition modules, provider routing/runtime adapters, memory/search services, API routes, and turn/session artifacts.

Exit evidence: unit tests for parsing, routing, prompt rendering, memory/search boundaries, and service/API behavior; artifact assertions for any accepted model proposal that can change durable state.

## Guidance

When adding model-facing behavior:

1. Decide what the model may propose and what the application must decide.
2. Put model output behind a bounded parser or typed schema.
3. Treat retrieved memory, web evidence, tool output, and external content as untrusted context.
4. Record enough artifact evidence to inspect the decision later.
5. Express durable behavior through services, schemas, and artifacts.

When adding provider behavior:

1. Keep provider adapters responsible for protocol serialization and response parsing.
2. Keep provider selection, fallback, cloud escalation, and refusal handling in application-owned routing/services.
3. Route provider-native tools through application capability and authorization contracts.
4. Preserve prompt authority boundaries when converting to provider-specific message formats.

When adding tools, skills, MCP, plugins, or agents:

1. Use one application-owned capability identity and permission model.
2. Require explicit approval for side effects, external writes, privileged delegation, and cloud transmission where policy requires it.
3. Treat third-party declarations as claims until an application or operator trust decision exists.
4. Feed results back through the same turn/session artifact path.
5. Keep ordinary non-agent interaction functional when agent features are disabled.

## Evidence

Implementation:

- `backend/app/cognition/prompt_envelope.py`
- `backend/app/cognition/prompt_assembler.py`
- `backend/app/cognition/prompt_renderer.py`
- `backend/app/cognition/prompt_chat_renderer.py`
- `backend/app/cognition/search_policy.py`
- `backend/app/cognition/memory_extraction.py`
- `backend/app/personality/policy.py`
- `backend/app/personality/schema.py`
- `backend/app/conversation/states.py`
- `backend/app/conversation/turn_manager.py`
- `backend/app/conversation/engine.py`
- `backend/app/conversation/continuity_policy.py`
- `backend/app/routing/provider_router.py`
- `backend/app/runtimes/llm/provider_runtime.py`
- `backend/app/services/llm_provider_service.py`
- `backend/app/services/llm_execution_coordinator.py`
- `backend/app/services/search_service.py`
- `backend/app/memory/curation_contract.py`
- `backend/app/memory/curation.py`
- `backend/app/services/memory_service.py`
- `backend/app/api/routes/memory.py`
- `desktop/src/components/memory-panel.js`

Tests:

- `backend/tests/unit/cognition/test_prompt_assembler.py`
- `backend/tests/unit/cognition/test_search_policy.py`
- `backend/tests/unit/cognition/test_memory_extraction.py`
- `backend/tests/unit/personality/test_personality.py`
- `backend/tests/unit/conversation/test_states.py`
- `backend/tests/unit/conversation/test_engine.py`
- `backend/tests/unit/conversation/test_continuity_policy.py`
- `backend/tests/unit/routing/test_provider_router.py`
- `backend/tests/unit/runtimes/llm/test_provider_runtime.py`
- `backend/tests/unit/services/test_llm_provider_service.py`
- `backend/tests/unit/services/test_llm_execution_coordinator.py`
- `backend/tests/unit/services/test_search_service.py`
- `backend/tests/unit/memory/test_curation_contract.py`
- `backend/tests/unit/memory/test_semantic_lifecycle.py`
- `backend/tests/unit/services/test_memory_service.py`
- `backend/tests/unit/api/test_memory_routes.py`

External practice reviewed:

- OpenAI Agents SDK documentation: [tools, guardrails, handoffs, sessions, human-in-the-loop, and tracing](https://openai.github.io/openai-agents-python/).
- Model Context Protocol documentation: [2026-07-28 specification](https://modelcontextprotocol.io/specification/2026-07-28), [authorization](https://modelcontextprotocol.io/specification/2026-07-28/basic/authorization), [elicitation](https://modelcontextprotocol.io/specification/2026-07-28/client/elicitation), and tool/capability discovery boundaries.
- Microsoft agent guidance: human-in-the-loop approval and agent runtime boundaries.
