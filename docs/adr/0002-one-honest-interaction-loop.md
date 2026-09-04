# 0002 - One Honest Interaction Loop

Date: 2026-09-01
Status: Implemented
Related: 0001, 0003, 0004, 0005

## Context and Problem Statement

JARVISv7 is a local-first, voice-first desktop assistant. It needs one durable interaction loop for text, push-to-talk, wake, resident voice, memory, search, artifacts, status, interruption, degraded states, and future action/agent behavior.

Without a single loop, desktop UI, scripts, voice services, memory, search, and later tools or agents can drift into separate products with different state, policy, evidence, and failure semantics.

## Decision Drivers

- Text and voice interactions must share cognition, personality, memory, policy, and artifact behavior.
- User-facing state needs to be inspectable through backend-owned session/status APIs.
- Voice-specific behavior should stay at the modality boundary: capture, STT, TTS, playback, wake, and interruption.
- Memory ingestion must come from committed turn/session artifacts rather than surface-specific transcripts.
- Desktop, scripts, daemon discovery, and future clients should render backend loop state instead of owning assistant behavior.

## Considered Options

- Build separate text and voice flows with shared helper functions.
- Put the primary loop in the desktop shell and call backend runtimes as services.
- Use backend `TurnEngine` as the committed interaction-loop authority, with modality-specific ingress delegating into it.

## Decision Outcome

Chosen option: `Use backend TurnEngine as the committed interaction-loop authority`.

Every normal assistant interaction that can affect session state, continuity, memory, tools, artifacts, or later agent behavior enters `TurnEngine` directly or through a service wrapper that delegates to it.

The committed loop is:

1. Session state is created and owned by `SessionService` and `SessionManager`.
2. Text input enters through `/task/text`, `turn_service.run_text_turn()`, or script callers.
3. Voice input enters through PTT, wake, resident voice, or script capture paths.
4. Voice is converted to transcript by the selected STT runtime.
5. Text and voice converge in `TurnEngine._run_reasoning_path()`.
6. The reasoning path assembles personality, continuity, retrieved memory, and optional search context.
7. The selected LLM runtime produces a response.
8. Voice turns synthesize and play TTS when available; text turns return response text directly.
9. Turn results record transcript, response, final state, runtime context, phase timings, failure phase, search evidence, interruptions, and degradation.
10. The engine records a `TurnArtifact`, updates working/episodic memory through the shared artifact path, and leaves semantic curation to the governed review pipeline.
11. Session timelines and turn artifacts preserve enough evidence to inspect what happened.

## Consequences

Positive:
- Text and voice share cognition, personality, memory context, runtime policy, artifacts, memory ingestion, and state semantics.
- Desktop and script clients can inspect a consistent loop through backend API state and artifacts.
- Failures can be attributed to phases such as capture, STT, LLM, TTS, playback, search, or turn-state.
- Resident voice, wake, interruption, and follow-up behavior can evolve around the loop without bypassing it.
- Later memory, action, skill, plugin, MCP, and agent work has one turn/session boundary for state, approval, recovery, and evidence.

Negative:
- The loop is deliberately backend-centered, which limits quick UI-only shortcuts.
- Voice capture, STT, reasoning, and TTS are coordinated through committed turns; lower-latency duplex behavior requires new architecture rather than hidden shortcuts.
- Barge-in and follow-up behavior depends on mode-specific wrappers around the committed turn.
- Every new surface must preserve backend-owned state, artifact, and memory boundaries.

## Implementation

The core loop lives in `backend/app/conversation/engine.py`.

`TurnEngine.run_text_turn()` creates a text turn and sends it directly to the shared reasoning path. `TurnEngine.run_voice_turn()` creates a voice turn, advances through listening/transcribing, calls STT, persists raw audio when available, then sends the transcript to the same reasoning path.

Conversation state is explicit. `ConversationState` defines bootstrap, profiling, idle, listening, transcribing, reasoning, acting, responding, speaking, interrupted, recovering, and failed states. `TurnContext.advance()` validates transitions and records phase timestamps.

Ingress stays thin:

- `/task/text` calls `turn_service.run_text_turn()` with the active session engine.
- `/session/ptt` enters through `SessionService`.
- `scripts/run_jarvis.py` calls `turn_service.run_text_turn()` or `turn_service.run_voice_turn()`.
- Desktop commands in `desktop/src-tauri/src/backend.rs` call backend routes; `desktop/src/api-client.js` centralizes the frontend API boundary.

Resident voice wraps the committed turn engine. `ResidentVoiceInvocationService` handles PTT, wake, hands-free, continuous, follow-up, and barge-in request queuing. `RealtimeConversationSession` records realtime events and live status, then delegates committed voice turns to `TurnEngine`.

Session state is observable through backend routes:

- `/session/status`
- `/session/search/cancel`
- `/status/desktop`
- `/status/resident-voice`
- `/status/wake`
- `/readiness`
- `/daemon/status`

The backend is the daemon boundary for this loop. `scripts/run_backend.py` acquires same-repo ownership for the configured loopback endpoint before serving and writes ephemeral discovery metadata to `cache/daemon/backend.json` with an adjacent lock file. `/daemon/status` exposes public daemon identity without exposing the local token, and `/daemon/shutdown` accepts only the token from local metadata. Desktop startup reads the same cache metadata, connects to a healthy same-repo daemon when present, and otherwise starts `scripts/run_backend.py`.

Artifacts preserve loop evidence and form the shared memory ingestion boundary. `TurnArtifact` records modality, transcript, prompt, retrieved memory, invoked search providers, reserved action/approval/delegated-run fields, search evidence, response, raw audio path, interruptions, final state, degradation, runtime context, phase timings, and failure phase. `SessionArtifact` and `SessionTimeline` preserve session-level evidence.

Memory is fed from the shared turn path. During reasoning, the engine retrieves working, episodic, and semantic context for both text and voice turns. After a successful committed turn, the engine records the artifact, updates bounded working memory, writes eligible episodic memory, and leaves durable semantic extraction to governed curation over persisted session and turn artifacts.

The loop is guarded against overlap. `TurnEngine` admits only one active turn per engine and rejects concurrent turns. Session close waits for active turn completion or reports that the turn is still cancelling.

Interruption is application-owned. Barge-in detection can stop playback, record interruption/recovery events, and queue a follow-up in supported modes. Search cancellation uses the same session/turn identity and returns through explicit turn state and search evidence.

Degraded behavior is part of the loop. TTS unavailability can still return text. Wake unavailability falls back to PTT-only behavior. Missing or empty STT/LLM output becomes explicit failure state and reason.

## Confirmation

Implementation files:
- `backend/app/conversation/engine.py`
- `backend/app/conversation/states.py`
- `backend/app/conversation/turn_manager.py`
- `backend/app/conversation/session_manager.py`
- `backend/app/conversation/realtime/session.py`
- `backend/app/conversation/realtime/ledger.py`
- `backend/app/conversation/realtime/interruption.py`
- `backend/app/artifacts/turn_artifact.py`
- `backend/app/artifacts/session_artifact.py`
- `backend/app/artifacts/session_timeline.py`
- `backend/app/services/turn_service.py`
- `backend/app/services/session_service.py`
- `backend/app/services/resident_voice_invocation.py`
- `backend/app/services/wake_monitor.py`
- `backend/app/services/audio_stream.py`
- `backend/app/services/utterance_segmenter.py`
- `backend/app/services/daemon_registry.py`
- `backend/app/api/routes/task.py`
- `backend/app/api/routes/session.py`
- `backend/app/api/routes/status.py`
- `backend/app/api/routes/readiness.py`
- `backend/app/api/routes/daemon.py`
- `backend/app/api/routes/memory.py`
- `backend/app/api/routes/memory_curation.py`
- `backend/app/runtimes/stt/`
- `backend/app/runtimes/tts/`
- `backend/app/runtimes/wake/`
- `scripts/run_jarvis.py`
- `scripts/run_backend.py`
- `desktop/src/`
- `desktop/src/api-client.js`
- `desktop/src-tauri/src/backend.rs`

Test coverage:
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
- `desktop/tests/static.test.mjs`

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration`
- `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families turn,voice,desktop --devices ...` for live host/device validation claims
- `npm --prefix desktop test` for desktop contract changes

## Follow-up

None for this ADR.

Future lower-latency duplex voice, TUI/client streaming, generalized tool execution, or agent delegation should update this ADR when they preserve the same loop architecture, or create/supersede an ADR when they change it.
