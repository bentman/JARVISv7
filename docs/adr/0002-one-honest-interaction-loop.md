# 0002 - One Honest Interaction Loop

## Status

Accepted, living.

## Context

JARVISv7 is a local-first, voice-first assistant. The second project promise is one complete interaction loop:

1. The user invokes the assistant.
2. JARVIS listens or receives text.
3. Speech becomes text when the input is voice.
4. The request enters one cognition path.
5. A response is formed under the active personality and policy context.
6. Speech is produced when available.
7. The user may interrupt.
8. The system returns to a clear, recoverable state.

Modern assistant and coding-agent systems generally converge on a similar principle: many surfaces may exist, but durable behavior lives in one loop. UI clients render, stream, approve, and inspect backend-owned interaction state.

That principle matters here because desktop, CLI, future TUI, resident voice, wake, text, memory, tools, and agents need one state, policy, artifact, and failure model.

## Decision

JARVISv7 uses `TurnEngine` as the committed interaction-loop authority. Every normal assistant interaction that can affect session state, continuity, memory, tools, or later agent behavior must enter this engine or a service wrapper that delegates to it. Text and voice enter through different ingress paths, but both converge on the same reasoning path and produce the same kind of result, status, artifact, and session continuity.

Setup, diagnostics, readiness probes, validation, and configuration operations support the loop. User-facing assistant interactions enter the loop when they affect session state, continuity, memory, tools, artifacts, or agent behavior.

The current loop is:

1. Session state is created and owned by `SessionService` and `SessionManager`.
2. Text input enters through `/task/text`, `turn_service.run_text_turn()`, or script callers.
3. Voice input enters through PTT, wake, resident voice, or script capture paths.
4. Voice is converted to a transcript by the selected STT runtime.
5. Text and voice converge in `TurnEngine._run_reasoning_path()`.
6. The reasoning path assembles personality, continuity, retrieved memory, and optional search context.
7. The selected LLM runtime produces a response.
8. Voice turns synthesize and play TTS when available; text turns return response text directly.
9. Turn results record transcript, response, final state, runtime context, phase timings, failure phase, search evidence, interruptions, and degradation.
10. The engine records a `TurnArtifact`, updates working/episodic memory through the shared artifact path, and leaves semantic curation to the governed review pipeline.
11. Session timelines and turn artifacts preserve enough evidence to inspect what happened.

Voice and text are modalities of one assistant loop.

## Current Design

The core loop lives in `backend/app/conversation/engine.py`.

`TurnEngine.run_text_turn()` creates a text turn and sends it directly to the shared reasoning path. `TurnEngine.run_voice_turn()` creates a voice turn, advances through listening/transcribing, calls STT, persists raw audio when available, then sends the transcript to the same reasoning path.

Conversation state is explicit. `ConversationState` defines bootstrap, profiling, idle, listening, transcribing, reasoning, acting, responding, speaking, interrupted, recovering, and failed states. `TurnContext.advance()` validates transitions and records phase timestamps.

Resident voice wraps the committed turn engine. `ResidentVoiceInvocationService` handles PTT, wake, hands-free, continuous, follow-up, and barge-in request queuing. `RealtimeConversationSession` records realtime events and live status, then delegates committed voice turns to `TurnEngine`.

Session state is observable. `/session/status`, `/status/desktop`, `/status/resident-voice`, and `/status/wake` expose active state, latest transcript/response, invocation source, voice diagnostics, wake status, resident stream health, barge-in support, phase timings, and failure phase.

The backend is the natural daemon boundary for this loop. A daemon contract makes the existing FastAPI process the single local authority for runtime selection, sessions, turn execution, artifacts, memory, resident voice, wake state, diagnostics, and future client coordination.

The first daemon-boundary slice is implemented around the existing FastAPI backend. `scripts/run_backend.py` acquires same-repo ownership for the configured loopback endpoint before serving and writes ephemeral discovery metadata to `cache/daemon/backend.json` with an adjacent lock file. `/daemon/status` exposes public daemon identity without exposing the local token, and `/daemon/shutdown` accepts only the token from the local metadata. Desktop startup reads the same cache metadata, connects to a healthy same-repo daemon when present, and otherwise starts `scripts/run_backend.py`.

Artifacts preserve loop evidence and form the shared memory ingestion boundary. `TurnArtifact` records modality, transcript, prompt, retrieved memory, tools, search evidence, response, raw audio path, interruptions, final state, degradation, runtime context, phase timings, and failure phase. `SessionTimeline` records ordered session events.

Memory is fed from the shared turn path. During reasoning, the engine retrieves working, episodic, and semantic context for both text and voice turns. After a successful committed turn, the engine records the artifact, updates bounded working memory, writes eligible episodic memory, and leaves durable semantic extraction to governed curation over persisted session and turn artifacts. Surfaces request memory changes through backend memory services.

The loop is guarded against overlap. `TurnEngine` admits only one active turn per engine and rejects concurrent turns. Session close waits for active turn completion or reports that the turn is still cancelling.

Interruption is implemented as application-owned state, not model-owned control. Barge-in detection can stop playback, record interruption/recovery events, and queue a follow-up in supported modes. Search cancellation also returns through interrupted/recovering/idle state when applicable.

Degraded behavior is part of the loop. TTS unavailability can still return text. Wake unavailability falls back to PTT-only behavior. Missing or empty STT/LLM output becomes explicit failure state and reason.

## Surfaces

Current surfaces:

- Desktop UI: resident voice, wake, status, settings, diagnostics, and conversation surfaces.
- Backend API: session, task, status, readiness, diagnostics, personality, memory, and provider routes.
- Scripts: `run_jarvis.py`, `run_backend.py`, validation, bootstrap, and model setup paths.

Future TUI work becomes another client surface for the same loop. It uses the backend/session/turn contracts and renders the same state and artifacts.

A local daemon shape is appropriate for coordinating desktop, CLI/script, and future TUI surfaces. The useful parts are a single running backend authority, loopback-only API, discovery for clients, single-instance ownership, local client authentication, shared event streaming, and client auto-connect/start behavior. These are client/process concerns around the loop, not new cognition or memory paths.

## Consequences

Benefits:

- Text and voice share cognition, personality, memory context, runtime policy, artifacts, memory ingestion, and state semantics.
- Desktop and future clients can inspect a consistent loop through API state and artifacts.
- Failures can be attributed to phases such as capture, STT, LLM, TTS, playback, or turn-state.
- Resident voice features can evolve around the loop without bypassing it.
- Later promises, especially memory, governed tools, skills, and agents, can attach to one loop.
- Memory policy stays enforceable because committed turns produce one artifact shape regardless of source surface.

Costs:

- The current loop is more synchronous than conversational. Voice capture, STT, reasoning, and TTS are coordinated in sequence with limited streaming overlap.
- Realtime behavior exists mostly as a wrapper around committed turn execution, not as a fully duplex assistant runtime.
- Barge-in and follow-up behavior is mode-dependent and not uniformly available across PTT, wake, hands-free, and continuous operation.
- Smoothness and latency depend on fixed capture windows, heuristic endpointing, runtime warmup, selected local model speed, and audio device behavior.
- Every new surface must respect the backend loop contract, which limits quick UI-only shortcuts.

## Remaining Work

- Improve perceived latency with clearer phase budgets, streaming response behavior, faster first audio, and better cold/warm runtime reporting.
- Harden wake reliability with stronger live validation, configurable thresholds, better noisy-room behavior, and clearer false-negative/false-positive diagnostics.
- Improve recovery quality for no-speech, empty transcript, playback failure, interrupted turns, cancelled searches, and runtime degradation.
- Make interruption and follow-up behavior more consistent across modes, while keeping explicit operator control.
- Expand end-to-end validation beyond unit/state coverage into repeatable live desktop, voice, wake, barge-in, and text-loop checks.
- Define a TUI client that talks to the same backend/session/turn APIs and renders state, output, diagnostics, approvals, and artifacts without forking the loop.
- Extend the backend-as-daemon boundary beyond the first desktop/script slice with shared event streaming and future TUI client behavior.
- Keep tool/action execution visible in the same turn artifact model as later governed-tool work arrives.
- Preserve a single assistant identity across desktop, API, scripts, and TUI: same session semantics, same personality policy, same memory boundaries, same failure language.
- Remove or avoid any surface-level shortcut that can create user-visible assistant behavior without producing a normal turn result and memory-eligible artifact.

This ADR establishes the interaction-loop dependency for later tool, memory, skill, plugin, and agent architecture. Those systems enter through, report through, recover through, and emit evidence through the same interaction loop.

## Implementation Path

Make loop changes by keeping `backend/app/conversation/engine.py` as the committed turn authority:

1. Add ingress or client behavior through `backend/app/services/`, `backend/app/api/routes/`, scripts, or desktop components that delegate to existing services.
2. Keep state transitions in `backend/app/conversation/states.py` and `backend/app/conversation/turn_manager.py`.
3. Keep prompt, personality, retrieval, search, and response assembly in the existing cognition and conversation path.
4. Record new evidence in `backend/app/artifacts/turn_artifact.py` or session artifacts before adding new UI display.
5. Add desktop/TUI/daemon surfaces as clients of backend APIs, not as new cognition or memory owners.
6. Validate with focused unit tests under `backend/tests/unit/conversation/`, `backend/tests/unit/services/`, `backend/tests/unit/api/`, and desktop static tests when UI contracts change.

Dependencies: loop changes depend on `TurnEngine`, session services, state transitions, prompt assembly, memory retrieval, artifacts, and status APIs.

Targets: backend services and routes for ingress, desktop or future TUI clients for rendering, daemon discovery for process ownership, and artifact schemas for evidence.

Exit evidence: unit tests for changed state transitions and services, API tests for changed routes, desktop/static tests for changed client contracts, and runtime/live tests only when audio, wake, or desktop behavior changes.

## Guidance

When adding an input surface:

1. Enter through `SessionService`, `TurnEngine`, or an explicit service wrapper that delegates to them.
2. Use existing session IDs, turn IDs, state transitions, status responses, and artifacts.
3. Keep modality-specific behavior at the boundary: capture, display, keyboard interaction, terminal rendering, or audio handling.
4. Keep cognition, personality, memory assembly, tool policy, and artifact persistence in backend services.
5. Route working, episodic, and semantic memory changes through backend memory services.

When adding daemon/client behavior:

1. Treat the backend process as the local daemon authority.
2. Keep clients thin: desktop, CLI/script, and TUI connect to daemon APIs for user-facing turns.
3. Use discovery, ownership, and authentication to decide which process owns the loop.
4. Stream state from the daemon so clients render the same turn, voice, wake, memory, diagnostics, and failure truth.
5. Keep memory ingestion behind committed turn/session artifacts.

When adding voice behavior:

1. Preserve the path from audio to transcript to shared reasoning.
2. Record capture diagnostics and phase timings.
3. Report unavailable/degraded runtime paths explicitly.
4. Route interruption and recovery through application state.
5. Validate with focused unit coverage first, then live runtime tests when hardware or audio behavior changes.

When adding tool or agent behavior:

1. Keep the turn loop as the outer control boundary.
2. Record attempted tools, approvals, failures, and results in turn/session evidence.
3. Make cancellation, recovery, and final state visible through the same status and artifact model.
4. Feed memory only from the resulting committed turn artifact and governed curation path.
5. Keep agent session state attached to the root session until a later ADR defines a narrower owned state.

## Evidence

Implementation:

- `backend/app/conversation/engine.py`
- `backend/app/conversation/states.py`
- `backend/app/conversation/turn_manager.py`
- `backend/app/conversation/session_manager.py`
- `backend/app/conversation/realtime/session.py`
- `backend/app/conversation/realtime/ledger.py`
- `backend/app/artifacts/turn_artifact.py`
- `backend/app/artifacts/session_timeline.py`
- `backend/app/services/turn_service.py`
- `backend/app/services/session_service.py`
- `backend/app/services/resident_voice_invocation.py`
- `backend/app/services/wake_monitor.py`
- `backend/app/services/audio_stream.py`
- `backend/app/services/utterance_segmenter.py`
- `backend/app/services/daemon_registry.py`
- `backend/app/runtimes/stt/`
- `backend/app/runtimes/tts/`
- `backend/app/runtimes/wake/`
- `backend/app/api/routes/task.py`
- `backend/app/api/routes/session.py`
- `backend/app/api/routes/status.py`
- `backend/app/api/routes/readiness.py`
- `backend/app/api/routes/daemon.py`
- `scripts/run_jarvis.py`
- `scripts/run_backend.py`
- `desktop/src/`
- `desktop/src-tauri/src/backend.rs`

Tests:

- `backend/tests/unit/conversation/`
- `backend/tests/unit/conversation/realtime/`
- `backend/tests/unit/services/test_turn_service.py`
- `backend/tests/unit/services/test_session_service.py`
- `backend/tests/unit/services/test_resident_voice_invocation.py`
- `backend/tests/unit/services/test_resident_voice_modes.py`
- `backend/tests/unit/services/test_wake_monitor.py`
- `backend/tests/unit/services/test_daemon_registry.py`
- `backend/tests/unit/api/test_routes.py`
- `backend/tests/unit/scripts/test_run_backend_script.py`
- `backend/tests/integration/services/test_two_turn_session.py`
- `backend/tests/integration/api/test_headless_client.py`
- `backend/tests/runtime/turn/`
- `backend/tests/runtime/voice/`
- `backend/tests/runtime/desktop/`
- `backend/tests/runtime/acceleration_matrix/test_acceleration_matrix.py`
