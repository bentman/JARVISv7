# 0003 - Mind with Boundaries

Date: 2026-09-01
Status: Implemented
Related: 0002, 0004, 0005, 0006, 0007

## Context and Problem Statement

JARVISv7 uses models for interpretation, synthesis, classification, extraction, and proposals. The application still needs to own state, prompt authority, provider routing, search privacy, memory lifecycle, artifacts, degraded behavior, interruption, and failure recovery.

Without an explicit model/application boundary, model output could become hidden control over memory, policy, tools, settings, search, providers, or future agents.

## Decision Drivers

- Model output must be useful without becoming application authority.
- Prompt inputs need explicit provenance and trust labels.
- Personality should affect style without changing safety, routing, memory, or action policy.
- Search, memory extraction, and later tool calls need typed proposal/validation boundaries.
- Provider selection, fallback, cloud escalation, and failure classification must remain application-owned.
- Durable state changes need service ownership and artifact evidence.

## Considered Options

- Let model prompts carry most policy and rely on model compliance.
- Use provider-native behavior directly whenever available.
- Treat the model as a bounded worker and require application-owned contracts before model output can affect durable state or side effects.

## Decision Outcome

Chosen option: `Treat the model as a bounded worker`.

The application owns session and turn state, prompt assembly, personality policy boundaries, provider routing, search planning, memory proposal validation, runtime readiness, artifacts, and status reporting. The model may produce natural-language responses, structured classifications, search plans, memory candidates, and future tool or agent proposals. Those outputs become trusted only after application-owned parsing, validation, authorization, or review.

## Consequences

Positive:
- Prompts can include useful context without giving that context policy authority.
- Personality can vary style without changing safety, routing, memory, or action rules.
- Model-proposed memory cannot silently become durable truth.
- Provider differences are hidden behind adapter contracts while product policy stays local.
- Search and retrieval evidence can improve answers without becoming instructions.
- Tools, skills, MCP, plugins, and agents have a boundary to attach to when later ADRs implement them.

Negative:
- More behavior must pass through typed contracts, parsers, services, and status surfaces.
- Some useful model autonomy is delayed until authorization and evidence paths exist.
- Provider-native features need wrapping when they bypass application policy.
- Experiments around tools and agents have more friction because side effects must fit application-owned contracts.

## Implementation

Prompt construction uses explicit authority. `PromptEnvelope` stores segments with `authority`, `content_type`, and `trusted` flags. `assemble_prompt_envelope()` separates application rules, personality style, session continuity, working memory, retrieved context, user input, and output contract. Renderers preserve those boundaries for provider-specific calls.

Personality owns style. `compile_personality_policy()` turns a profile into response guidance and examples, while safety, tool, routing, memory, and factual-grounding policy remain application-owned. Personality schemas reject hidden authority fields.

Conversation state is deterministic. `ConversationState` and `TurnContext.advance()` define legal transitions, interruption behavior, recovery state, session closure, and final artifact shape.

Provider routing is application-owned. `RoutedLLM` selects primary, fallback, or cloud profile according to saved selection and explicit user request. It classifies provider failures before fallback and records attempt evidence. Provider adapters serialize prompt envelopes into each provider protocol.

Search uses a bounded planning boundary. `SearchIntentResolver` treats model output as a strict `SearchPlan`, rejects secrets, asks for confirmation before private outbound queries, limits query count, and sends only public-topic queries to search providers. `ground_search_prompt()` treats web evidence as untrusted tool context and requires cited, bounded synthesis.

Memory extraction is proposal-only. `MemoryCandidateExtractor` asks the model for bounded JSON candidates from persisted turn fields. `parse_model_proposals()` strictly parses the shape. `verify_evidence_refs()` checks source turn, source field, and exact excerpt. Provisional candidates remain review-only until application-owned lifecycle decisions create governed facts.

Memory lifecycle is service-owned. `/memory` routes expose policy, inspection, confirmation, correction, dispute, and forgetting through `MemoryService`.

Action governance has contract scaffolding. `backend/app/actions/contracts.py` defines capability descriptors, model action proposals, effect classes, authorization context and decisions, approval audit records, execution result records, and a small registry. These contracts preserve the boundary for later executable action work, but are not yet the general model-callable execution path.

LLM execution is coordinated. `LLMExecutionCoordinator` gives interactive work priority over background curation and blocks new interactive work during shutdown drain.

Backend and desktop boundaries reinforce these rules. Desktop surfaces call backend APIs for cognition, memory lifecycle, provider configuration, state transitions, and status. Desktop memory controls call backend-owned lifecycle APIs rather than editing memory directly.

## Confirmation

Implementation files:
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
- `backend/app/services/llm_provider_profiles.py`
- `backend/app/services/llm_provider_service.py`
- `backend/app/services/llm_execution_coordinator.py`
- `backend/app/services/search_service.py`
- `backend/app/actions/contracts.py`
- `backend/app/memory/curation_contract.py`
- `backend/app/memory/curation.py`
- `backend/app/services/memory_service.py`
- `backend/app/api/routes/memory.py`
- `backend/app/api/routes/llm_config.py`
- `desktop/src/components/memory-panel.js`
- `desktop/src/components/llm-provider-settings.js`
- `desktop/src/api-client.js`

Test coverage:
- `backend/tests/unit/cognition/test_prompt_assembler.py`
- `backend/tests/unit/cognition/test_search_policy.py`
- `backend/tests/unit/cognition/test_memory_extraction.py`
- `backend/tests/unit/personality/test_personality.py`
- `backend/tests/unit/conversation/test_states.py`
- `backend/tests/unit/conversation/test_engine.py`
- `backend/tests/unit/conversation/test_continuity_policy.py`
- `backend/tests/unit/routing/test_provider_router.py`
- `backend/tests/unit/runtimes/llm/test_provider_runtime.py`
- `backend/tests/unit/services/test_llm_provider_profiles.py`
- `backend/tests/unit/services/test_llm_provider_service.py`
- `backend/tests/unit/services/test_llm_execution_coordinator.py`
- `backend/tests/unit/services/test_search_service.py`
- `backend/tests/unit/actions/test_action_contracts.py`
- `backend/tests/unit/memory/test_curation_contract.py`
- `backend/tests/unit/memory/test_semantic_lifecycle.py`
- `backend/tests/unit/services/test_memory_service.py`
- `backend/tests/unit/api/test_memory_routes.py`
- `backend/tests/unit/api/test_llm_config_routes.py`

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration` when memory curation or route integration changes

## Follow-up

None for this ADR.

Future executable tools, MCP, skills, plugins, and agents should preserve this model/application boundary. Those features should update this ADR when they change the boundary, or create/supersede an ADR when they introduce a different architecture.
