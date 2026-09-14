# 0005 - Governed Ability to Act

Date: 2026-09-01
Status: Implemented
Related: 0002, 0003, 0004, 0008, 0009

## Context and Problem Statement

JARVISv7 becomes useful when it can act: search, change settings, configure providers, manage memory lifecycle, call services, use tools, connect external capability, or delegate to agents. Acting must remain visible enough that the user can understand what happened, stop it, correct it, and distinguish low-risk reads from higher-risk side effects.

The architecture needs one governable action loop. A capability must have a stable identity, input contract, effect class, readiness/availability state, authorization rule, execution owner, timeout/cancellation behavior, result shape, artifact evidence, and user-facing unavailable explanation.

## Decision Drivers

- Action governance should be based on effect and risk, not feature label.
- Specific operator requests authorize the requested action without a second approval.
- External, mutating, privileged, destructive, privacy-sensitive, or cloud-transmitting actions need explicit authorization.
- Model output can request or propose an action, but application code must validate, authorize, execute, and record it.
- Action results and external content must return as untrusted context.
- Tools, search, provider configuration, memory lifecycle, MCP, skills, plugins, and agents need one evidence model.
- Preserve ADR 0002's turn ownership, ADR 0003's model/application authority boundary, and ADR 0004's memory lifecycle while action capability grows.

## Decision Outcome

Risk determines friction:

- Local read: inspect local state already in scope.
- Local write: change repo, config, memory, profile, or local files.
- External read: send a query or request outside the machine.
- External write: mutate a remote system or send a message.
- Cloud model: transmit prompt/context to a cloud LLM provider.
- Privileged execution: run shell/process, plugin code, agent process, or MCP server command.
- Destructive action: delete, overwrite, reset, purchase, transfer, publish, or otherwise hard-to-reverse work.

A clear, specific operator request authorizes that action, regardless of effect class or whether it arrives through a UI or natural language. The application validates scope, arguments, readiness, and execution boundaries and records authorization and execution evidence, without asking the operator to approve the same request again. This authority does not extend to additional actions proposed by the model. Those proposals follow the effect-based authorization rules, including explicit approval for private outbound context and other approval-required operations.

## Consequences

Positive:
- Action can grow without each feature inventing its own trust model.
- Low-risk operations stay usable because governance is tied to effect, not form.
- The user sees meaningful approval prompts where authority or risk changes.
- Search, provider routing, memory lifecycle, tools, MCP, plugins, skills, and agents can share one evidence model.
- Prompt injection and model mistakes are easier to contain because external content and tool output remain untrusted context.

Negative:
- A unified action model requires shared infrastructure before broad model-callable tool use is enabled.
- Provider-native tool features need wrapping before they can participate safely.
- Approval UX must be designed carefully or useful automation will feel blocked.
- Capability metadata can become stale unless readiness and health checks are real observations.
- More artifact detail is needed as actions become more capable.

## Implementation

### Capability contract and registry

`backend/app/actions/contracts.py` defines capability descriptors, proposals, authorization decisions, approval records, execution results, cancellation records, and the capability registry. Registration validates schemas, availability, effect classes, execution boundaries, metadata trust, and duplicate identities. `APPROVAL_EFFECT_CLASSES` supplies the default authorization posture; private-context search, executable plugin installation, and server-declared MCP tool effects use explicit approval rules.

### Authorization and execution

`backend/app/services/capability_service.py` owns proposal, authorization, execution, cancellation, and audit. It refreshes observed readiness and handler bindings, reports malformed descriptors individually, and revalidates parked proposals before approval. Pending proposals have bounded retention; repeated decisions are refused and secret-bearing arguments are masked.

`execute_operator_action` and `invoke_operator_capability` carry operator authorization while retaining the shared execution and evidence path. Dedicated extension invocation uses the latter. Model proposals still follow the approval ladder. `execute_authorized` supplies the turn-scoped execution entry point; the generic operator API refuses turn-boundary capabilities that require a conversation owner.

### Execution boundaries

`backend/app/actions/boundaries.py` enforces allowed storage roots, deadlines, cancellation, result limits, and process argv/environment/working-directory declarations. Process-bearing capabilities use these controls. They provide application-level containment, not an OS sandbox.

### Evidence

Action records are persisted and fsynced to `data/actions/action-log.jsonl`, with bounded rotation. Turn artifacts retain proposals, decisions, approvals, execution results, cancellations, search evidence, and delegated runs. Tool results enter prompts as untrusted context. `SessionCallOutcomeUnknownError` is preserved as `outcome_unknown` by capability execution.

### Boundaries owned elsewhere

Search records plans, provider attempts, sources, approval, cancellation, and failure evidence through `SearchIntentResolver`, `SearchService`, and `TurnEngine`. Provider routing observes cloud eligibility, endpoint and secret-store readiness, fallback policy, and attempt evidence. Settings writes are allowlisted and masked; memory lifecycle operations use service-owned revision checks and lifecycle events.

ADR 0003 owns model authority, ADR 0004 owns memory behavior, ADR 0009 owns the shared session lifecycle used by session-bearing capabilities, and ADR 0008 owns operator presentation of action evidence.

## Confirmation

Implementation files:
- `backend/app/actions/contracts.py`
- `backend/app/actions/catalog.py`
- `backend/app/actions/boundaries.py`
- `backend/app/actions/process.py`
- `backend/app/services/capability_service.py`
- `backend/app/services/search_service.py`
- `backend/app/artifacts/turn_artifact.py`

Test coverage:
- `backend/tests/unit/actions/test_action_contracts.py`
- `backend/tests/unit/actions/test_action_catalog.py`
- `backend/tests/unit/actions/test_action_boundaries.py`
- `backend/tests/unit/services/test_capability_service.py`
- `backend/tests/unit/artifacts/test_turn_artifact.py`
- `backend/tests/integration/test_extension_runtime.py` for operator-versus-model authorization through application services
- `backend/tests/fixtures/search_providers.py` and `backend/tests/fixtures/action_governance.py` supply deterministic action-path fixtures

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration` when authorization or evidence propagation changes
- `backend/.venv/Scripts/python scripts/validate_backend.py runtime --mock` for mock-based runtime coverage

## Follow-up

None for this ADR.

Future effect classes, approval modes, or a change to what a specific operator request authorizes should update this ADR when they preserve the same governance architecture, or create/supersede an ADR when they change it.
