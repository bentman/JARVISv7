## Brief summary

Slice T2 is a real corrective pass, not just documentation. The plan explicitly targets the prior scaffold-vs-active-runtime gap: lifecycle activation, truthful status, safe interruption termination, real mode state, active shared-stream PTT/wake, live barge-in proof, hands-free/continuous behavior, desktop proof, and governance closeout.

The changelog now records T2 evidence beyond the earlier T.1–T.8 unit/static scaffold. It includes AMD64 live proof for shared-stream PTT/wake, barge-in, hands-free, and desktop; then later ARM64 operator live proof for resident audio, wake shared-stream, barge-in follow-up, hands-free follow-up, and desktop resident voice tests.

## Alignment assessment

The main corrective gaps I previously flagged are mostly addressed.

The resident stream now has explicit API lifecycle control. `/status/resident-voice/start` starts the stream, rebuilds the engine through `bind_session`, and replaces the session engine so the active engine can receive interruption chunks; `/stop` mirrors this and rebuilds the engine after stopping.  `SessionService.replace_engine()` was added to preserve personality while swapping the active engine.

Status truth is improved. `/status/resident-voice` now returns a structured `stream` object, preserves legacy flat fields, reports stopped streams as degraded, and only reports `barge_in_supported` / `barge_in_wired` when the stream is running, VAD is configured, and the active engine has both detector and interruption chunks.  The schema reflects those fields.

The previous desktop/backend schema mismatch is fixed. The desktop now reads `status.stream` first and falls back to flat fields only as compatibility behavior. It renders stream-present, stream-running, barge-in-wired, follow-up state, and continuous state.

The interruption-monitor hang risk is directly addressed. `_play_with_interruption_monitor()` now polls chunks only while playback reports active, and exits normally when playback completes.   TTS playback now has `is_playing()` and bounded wait behavior.

Backend resident modes are now real state, not just labels. `ResidentVoiceInvocationService` supports `ptt-only`, `ptt+wake`, `hands-free`, and `continuous`; invalid modes are rejected; continuous sets explicit active state.   The API exposes mode mutation, and `ptt-only` stops wake monitoring.

Hands-free and continuous behavior now exists in backend code. After a successful non-follow-up turn, hands-free captures one follow-up utterance and continuous captures a follow-up under source `continuous`; follow-up status is exposed.

Desktop activation is now wired. Startup calls `ensureResidentVoiceStream()` before wake monitoring, mode changes can start the stream when needed, and the mode selector calls the backend mode endpoint.    Tauri/API client endpoints exist for stream start/stop and mode mutation.

## Remaining corrections or cautions

The biggest remaining governance issue: **`SYSTEM_INVENTORY.md` still has no Slice T / resident voice capability entry at the top.** The Slice T2 plan says T.17 should append inventory only after live proof and closeout criteria are satisfied.  The changelog now records live proof and T.17 completion, but the inventory still starts with Slice S and has no Slice T entry.  Add a constrained inventory entry with exact limitations: AMD64 and ARM64 live-proven, energy VAD only, no echo cancellation/overlapped speech claim, no browser audio path, and no Silero VAD.

Second: **stream shutdown should release the mic during backend shutdown.** The FastAPI lifespan cleanup currently stops the managed local LLM only.  Since the resident stream can now be started from desktop startup, add lifecycle cleanup for `resident_audio_stream.stop()` in the lifespan finalizer.

Third: **desktop startup now starts the resident stream automatically.** That is useful for voice-first behavior, but it should remain visibly reported and intentional. The code calls `ensureResidentVoiceStream()` during desktop start and restart.   This is not necessarily wrong, but the UI and inventory should describe it plainly: default desktop voice session starts the shared mic stream; hands-free/continuous remain explicit modes.

Fourth: **continuous mode appears bounded by follow-up capture windows, not a true infinite always-on conversational loop.** That matches the safer plan wording, but documentation should avoid overclaiming “continuous conversation” beyond “explicit continuous mode with bounded follow-up windows.” The implementation enqueues follow-up source `continuous` after a normal completed turn, but does not recursively follow up after a completed `continuous` turn because follow-up sources are excluded.

## Net status

The corrective run materially improves Slice T. The current state is no longer just scaffold. It now has active stream lifecycle, truthful status, safe interruption monitoring, mode mutation, desktop control wiring, and live proof recorded for both AMD64 and ARM64.

Recommended next action: add the missing `SYSTEM_INVENTORY.md` Slice T entry and a small shutdown cleanup patch for the resident audio stream.
