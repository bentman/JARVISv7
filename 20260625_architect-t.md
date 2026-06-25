Keep the current Python/Tauri/backend turn architecture, but add a thin **resident full-duplex voice layer** around it: one shared microphone stream, wake-word detection, VAD-based utterance boundaries, interrupt detection during TTS, and a queue handoff into the existing `TurnEngine`. Current PTT remains as the fallback/control path.

The repo already has many of the right pieces. What is missing is a continuous, low-latency audio coordinator that can keep the assistant “present” between committed turns.

## Grounding in the project vision

`ProjectVision.md` says JARVISv7 is “local-first, voice-first,” not “a chatbot with voice added later,” and the target interaction includes speaking naturally, interrupting, preserving turn continuity, and explicit degraded/failure states.

The root acceptance path specifically requires: user invokes the assistant, audio is captured, STT runs locally by default, the turn routes through the same cognition/execution engine used by all modalities, TTS speaks back locally when available, the user can interrupt and continue naturally, and failures are visible/recoverable.

The project’s intended voice stack is already defined: ONNX Whisper for STT, Kokoro ONNX for TTS, llama.cpp/Ollama/cloud-policy for LLM, and openWakeWord for wake detection.  That strongly argues against re-platforming voice capture into a browser-only path.

## What the current codebase appears to have

The current shape is turn-based, with several useful foundations already integrated.

The `TurnEngine` has a canonical `run_voice_turn(audio, sample_rate)` path. It advances through `LISTENING`, `TRANSCRIBING`, reasoning, response, optional TTS, artifact recording, memory retrieval, tools, session continuity, and personality styling.

The desktop does not appear to capture microphone audio in the browser. The Tauri frontend calls `invoke_resident_ptt`, which calls a backend `/session/ptt` endpoint.   The backend route enqueues resident PTT work through `ResidentVoiceInvocationService`.

That resident service currently defaults to `voice_service.capture_audio(duration_s=3.0)`, meaning the normal PTT turn captures a fixed three-second recording and then runs the turn.  The actual capture function uses `sounddevice.rec(...)` followed by `sd.wait()`, so this is blocking batch capture, not streaming conversational capture.

Wake-word support exists and is not just conceptual. `WakeMonitorService` runs a background thread, streams chunks from the mic, detects wake via a `WakeBase` runtime, keeps one second of pre-roll, then captures three seconds of post-wake command audio and invokes the resident voice callback.

The wake runtime is openWakeWord/ONNX-aligned. The repo’s `OpenWakeWordRuntime` loads `hey_jarvis_v0.1.onnx`, `melspectrogram.onnx`, and `embedding_model.onnx`, then calls `model.predict()` against 16 kHz int16 chunks.

There is also a realtime boundary, but it is not truly streaming yet. `RealtimeConversationSession.run_voice_invocation()` emits typed realtime events, captures or accepts already-captured audio, commits it, then calls `TurnEngine.run_voice_turn(...)`.  The inventory states this explicitly: Group M added typed realtime events, an in-memory event ledger, non-streaming response/interruption helpers, and a realtime voice invocation coordinator; committed turn execution remains owned by `TurnEngine`.

Barge-in is structurally present but too thin for natural conversation. The engine can play TTS with an interruption monitor if `barge_in_detector` and `interruption_audio_chunks` are supplied.  The detector itself is simple RMS energy with a guard time.  On detection, playback stops and interruption events are recorded, but the interrupted speech is not yet converted into the next committed user turn.

The inventory also confirms the same reality: Slice C has deterministic interruption and diagnostic proving host, but no full acoustic microphone barge-in validation.

## Main diagnosis

The current implementation is “turn-based voice with wake/PTT triggers,” not yet “resident conversation.”

The most important gap is not STT, TTS, LLM, memory, tracing, or session integration. Those already exist. The gap is the **audio-control layer before the turn is committed** and **during assistant speech**.

Right now, PTT captures a fixed window. Wake captures a fixed post-wake window. Interruption detects energy but does not become a natural follow-up turn. That is why it misses the vision target: the system can run voice turns, but it does not yet continuously manage listening, speech boundaries, silence, interruption, and recovery as a single resident interaction loop.

## Most appropriate architecture: additive resident voice coordinator

Add one backend service, conceptually:

`ResidentAudioCoordinator`

It should own the microphone stream and feed three consumers:

1. **Wake detector** while idle.
2. **VAD / utterance segmenter** while listening.
3. **Barge-in detector** while speaking.

It should hand only completed utterances into the existing `RealtimeConversationSession` / `TurnEngine` path. This preserves the current memory, tools, tracing, personality, artifacts, and session continuity. It does not replace the turn engine.

The current `WakeMonitorService`, `ResidentVoiceInvocationService`, and `RealtimeConversationSession` can remain, but the capture primitive should change from fixed-duration blocking capture to a shared streaming buffer.

## Recommended mechanism by capability

### 1. Microphone capture: replace blocking capture with one shared streaming input

Keep Python `sounddevice`, because the backend already uses it for mic and TTS, and the project vision is local-first/desktop-first. The existing blocking `sd.rec(...); sd.wait()` path is fine for proof, but it is structurally wrong for hands-free conversation.

Use `sounddevice.InputStream` with a callback into a thread-safe ring buffer. The `sounddevice` docs describe callback-based streams where PortAudio periodically calls the callback while the stream is active; for real-time audio, callbacks must avoid blocking work, allocation, file I/O, or unpredictable calls. ([Python Sounddevice][1])

Practical shape:

```text
InputStream callback
  -> normalize mono 16 kHz int16/float32 chunk
  -> append to ring buffer
  -> publish lightweight chunk event
       idle: wake detector
       listening: VAD segmenter
       speaking: barge-in detector
```

Do not run STT, LLM, file writes, or model loading inside the audio callback. The callback should only push chunks into a queue/ring.

### 2. Wake word: keep openWakeWord, but move it under the shared audio coordinator

The current openWakeWord implementation already matches the vision and runtime strategy. The upstream openWakeWord project is designed for voice-enabled applications, supports streaming detection, expects 16-bit 16 kHz PCM, and recommends frames in multiples of 80 ms for latency/efficiency tradeoffs. ([GitHub][2])

The repo’s `WAKE_CHUNK_SAMPLES = 1280` at 16 kHz equals 80 ms, which aligns well with openWakeWord guidance.

Keep:

```text
idle -> openWakeWord detects "hey jarvis" -> transition to LISTENING
```

Improve:

```text
1s pre-roll + VAD-driven command end
```

Instead of current fixed `WAKE_COMMAND_SECONDS = 3.0`, use wake detection to start listening, then use VAD to determine the end of the user’s utterance.

### 3. End-of-utterance: add VAD; do not use fixed command windows

For this project, the best default VAD is **Silero VAD ONNX**, because JARVISv7 already standardizes around ONNX/ONNX Runtime for voice families. Silero VAD supports ONNX Runtime usage, supports 8 kHz and 16 kHz sampling, is lightweight, and reports processing 30+ ms chunks in under 1 ms on one CPU thread, with ONNX sometimes faster. ([GitHub][3])

Use VAD to implement:

```text
speech_started when N consecutive speech frames
speech_ended when M ms of silence after speech
commit utterance if duration and energy are valid
discard if only wake/noise
```

Suggested defaults:

```text
sample_rate: 16000
frame: 30 ms or 80 ms depending model path
pre_speech_padding: 300-500 ms
post_speech_silence: 600-900 ms
max_utterance: 12-20 s
min_utterance: 250-400 ms
```

Keep **WebRTC VAD** as a fallback option, not primary. `py-webrtcvad` is simple and fast, but it only accepts 16-bit mono PCM at 8/16/32/48 kHz and frames of exactly 10, 20, or 30 ms. ([GitHub][4]) It is useful when Silero is unavailable, but Silero ONNX better matches the repo’s ONNX/hardware-readiness direction.

### 4. Barge-in: convert the current event boundary into a real interruption turn

The current code can stop playback if an interruption detector fires during TTS.  But to feel natural, interruption must do more than stop speech. It must capture what the user said and continue the conversation.

Recommended incremental behavior:

```text
SPEAKING
  mic stream remains active
  VAD detects user speech above echo/guard threshold
  stop TTS immediately
  ledger: USER_INTERRUPTION_DETECTED, ASSISTANT_SPEECH_STOP_REQUESTED, TURN_RECOVERING
  capture interrupted utterance from ring buffer
  commit as next voice turn with source="barge_in"
```

This reuses the existing realtime interruption ledger, which already records user interruption, speech stop request, and recovering state.

The existing `BargeInDetector` should not remain pure RMS energy. RMS alone will false-trigger on the assistant’s own TTS, keyboard noise, fans, or system audio. Replace or wrap it with:

```text
guard time after TTS starts
VAD speech probability
minimum speech duration
optional user/system echo suppression
optional wake/session policy
```

For first implementation, use Silero VAD + higher speech threshold during TTS + short guard time. Then add echo mitigation later.

### 5. TTS playback: keep current output path, but make it interruptible by default

The TTS playback module already has `start(audio, sample_rate)`, `play(...)`, and `stop()`. `play()` blocks on `sounddevice.wait()`, while `start()` returns after calling `sounddevice.play(...)`.

For hands-free UX, route all voice output through the non-blocking `start()` path with a monitor loop:

```text
tts.start()
while playing:
    check mic VAD/barge-in events
    check stop request
    emit speaking progress/state
tts.stop() on barge-in
```

This can be done without changing `TurnEngine` dramatically. The current `_play_with_interruption_monitor` already has the right seam; it just needs to receive live chunks from the resident audio coordinator rather than a test iterable.

### 6. Desktop UX: keep PTT, add modes rather than replacing controls

The desktop already renders wake state, voice state, capture state, session state, transcript, response, failure reason, and TTS device.  It also polls session status every second and wake status every 1.5 seconds.

Add mode controls:

```text
Voice Mode:
- PTT only
- Wake word
- Hands-free session
- Accessibility continuous listen
```

PTT should remain available in every mode as an explicit fallback.

Visible states should map directly to the existing vision list: idle, listening, transcribing, thinking/reasoning, speaking, interrupted, degraded, failed. The vision explicitly requires the user to understand those states.

### 7. Browser audio APIs: optional later, not primary now

Browser audio APIs are not the right primary move for this codebase. The current product is a Tauri desktop host controlling a local Python backend, and the voice runtimes live in Python/backend services. Re-routing microphone capture through browser `getUserMedia()` would require a bridge from the webview to Tauri/backend, new audio transport, new device/readiness semantics, and likely duplication of the existing backend voice path.

Browser APIs are still relevant as a possible later accessibility or web-shell path. `getUserMedia()` is the browser standard for microphone access and requires user permission and browser indicators. ([MDN Web Docs][5]) `AudioWorklet` is suitable for low-latency custom audio processing on a separate Web Audio thread. ([MDN Web Docs][6]) Browser capture also exposes `echoCancellation`, including browser-managed echo cancellation behavior. ([MDN Web Docs][7])

But adopting browser capture first would be a larger cross-boundary change than needed. For JARVISv7, the better path is:

```text
Primary: backend sounddevice resident stream
Optional later: webview AudioWorklet capture provider implementing same AudioCaptureProvider interface
```

## Implementation outline

### Phase 1 — Replace fixed-window capture with streaming capture, without changing turn semantics

Add:

```text
backend/app/services/audio_stream.py
```

Core types:

```text
AudioChunk
  samples_int16
  samples_float32
  sample_rate
  timestamp
  rms
  peak

ResidentAudioStream
  start()
  stop()
  subscribe(name)
  ring_buffer(seconds)
  latest(duration_s)
```

Modify `voice_service.capture_audio()` to optionally read from this stream for compatibility, but keep the existing function as fallback.

Acceptance criteria:

```text
/session/ptt still works
wake still works
TurnEngine unchanged
same artifacts/traces/memory generated
audio diagnostics report active stream state
```

### Phase 2 — Add VAD utterance segmentation

Add:

```text
backend/app/runtimes/vad/base.py
backend/app/runtimes/vad/silero_onnx.py
backend/app/runtimes/vad/webrtc.py  # fallback
backend/app/services/utterance_segmenter.py
```

Behavior:

```text
listen_until_utterance()
  include pre-roll
  wait for speech start
  wait for silence end
  return audio + sample_rate + diagnostics
```

Replace wake post-command fixed capture with VAD-based command capture.

Acceptance criteria:

```text
wake no-speech returns explicit "No speech detected after wake"
3-second hard cutoff no longer truncates normal user speech
long silence does not produce empty STT turns
```

### Phase 3 — Upgrade wake to resident mode

Refactor `WakeMonitorService` so it no longer owns its own `sounddevice.InputStream`. It should consume from `ResidentAudioStream`.

Current duplication:

```text
WakeMonitorService -> wake_chunk_source -> sounddevice.InputStream
PTT -> capture_audio -> sounddevice.rec
```

Target:

```text
ResidentAudioStream -> WakeMonitorService
ResidentAudioStream -> PTT capture / utterance segmenter
ResidentAudioStream -> barge-in monitor
```

Acceptance criteria:

```text
only one mic stream owner
wake and PTT cannot fight over the device
pause/resume wake around voice invocation still works
wake status still populates existing desktop panel
```

### Phase 4 — Make barge-in real

Update `_play_with_interruption_monitor` wiring so it receives live mic chunks from the resident stream while TTS is playing.

Then add a post-interruption capture path:

```text
on_barge_in:
  playback.stop()
  capture interruption utterance using VAD
  enqueue source="barge_in"
```

Do not recursively call `TurnEngine` from deep inside playback. Instead, record interruption, stop playback, and enqueue a new resident invocation through the same resident service queue. This keeps orchestration deterministic.

Acceptance criteria:

```text
assistant speech stops within a small bounded delay after user speech
interruption is recorded in realtime ledger
interrupted user speech becomes next committed turn
prior response is marked interrupted in artifact/session state
```

### Phase 5 — Add hands-free session mode

Hands-free should be explicit, not always-on by default.

Modes:

```text
ptt_only:
  existing behavior

wake:
  current wake behavior, VAD-improved

hands_free:
  after a successful wake or PTT turn, keep listening for follow-up utterances for a configurable window

accessibility_continuous:
  continuous listen with stronger visible indicators and explicit opt-in
```

Hands-free policy:

```text
after assistant finishes speaking:
  listen for follow-up for 8-15 seconds
  if speech -> commit next turn
  if silence -> idle/wake
```

This matches the project’s continuity goal without creating uncontrolled always-listening behavior.

### Phase 6 — Observability and readiness

Extend readiness/capabilities rather than inventing hidden behavior.

Add readiness flags:

```text
supports_resident_audio_stream
supports_vad
supports_hands_free
supports_barge_in_capture
supports_echo_mitigation
resident_voice_mode
vad_runtime
wake_runtime
barge_in_runtime
```

Add diagnostics:

```text
mic stream active
input device
sample rate
chunk size
dropped chunks
rms/peak
vad probability
wake score/threshold
current audio state
last utterance duration
last interruption reason
```

The project already emphasizes evidence-backed readiness and explicit failures.  This should be treated as part of the feature, not logging afterthought.

## Recommended final state (Shape - not pattern)

```text
Tauri desktop
  ├─ text input -> /task/text -> TurnEngine
  ├─ PTT button -> /session/ptt -> ResidentVoiceInvocationService
  ├─ wake controls -> /status/wake/*
  └─ status panels -> readiness/session/wake/realtime diagnostics

Python backend
  ├─ ResidentAudioCoordinator
  │    ├─ sounddevice InputStream
  │    ├─ ring buffer
  │    ├─ wake consumer: openWakeWord
  │    ├─ VAD consumer: Silero ONNX, WebRTC fallback
  │    └─ barge-in consumer: VAD + guard + playback stop
  │
  ├─ RealtimeConversationSession
  │    ├─ event ledger
  │    ├─ invocation source: ptt | wake | hands_free | barge_in
  │    └─ commit completed utterance
  │
  └─ TurnEngine
       ├─ STT
       ├─ memory/retrieval
       ├─ tool execution
       ├─ LLM
       ├─ personality/style
       ├─ TTS
       └─ artifacts/tracing
```

## Priority order

The best first step is **not** “natural conversation” as one feature. It is:

1. Add shared resident audio stream.
2. Add VAD utterance segmentation.
3. Replace fixed 3-second capture windows.
4. Feed wake/PTT through the same utterance path.
5. Wire live mic chunks into existing interruption seam.
6. Convert interruption into a queued follow-up turn.
7. Add hands-free session mode after wake/PTT.

This keeps the current integrated turn, memory, personality, tracing, and readiness architecture intact while moving the voice layer much closer to the project vision.

[1]: https://python-sounddevice.readthedocs.io/en/0.5.1/api/streams.html "Streams using NumPy Arrays — python-sounddevice, version 0.5.1"
[2]: https://github.com/dscripka/openWakeWord "GitHub - dscripka/openWakeWord: An open-source audio wake word (or phrase) detection framework with a focus on performance and simplicity. · GitHub"
[3]: https://github.com/snakers4/silero-vad "GitHub - snakers4/silero-vad: Silero VAD: pre-trained enterprise-grade Voice Activity Detector · GitHub"
[4]: https://github.com/wiseman/py-webrtcvad "GitHub - wiseman/py-webrtcvad: Python interface to the WebRTC Voice Activity Detector · GitHub"
[5]: https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia "MediaDevices: getUserMedia() method - Web APIs | MDN"
[6]: https://developer.mozilla.org/en-US/docs/Web/API/AudioWorklet "AudioWorklet - Web APIs | MDN"
[7]: https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackConstraints/echoCancellation "MediaTrackConstraints: echoCancellation property - Web APIs | MDN"
