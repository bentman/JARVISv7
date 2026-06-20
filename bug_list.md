# Bug List

## 2026-06-20 - PTT STT capture window and QNN Whisper transcript reliability

Status: Open

2026-06-20 update: The language-control portion was addressed separately from the PTT capture-window issue. JARVIS now has a global `JARVIS_LANGUAGE` setting, personality profiles expose `response_language`, prompt policy carries that language to local Ollama and llama.cpp, and QNN Whisper decode derives its prefix from tokenizer configuration instead of a fixed start token only. The PTT duration, empty transcript, audio diagnostics, and microphone contention items remain open.

Observed on Windows ARM64 Qualcomm profile after S.7 Adreno OpenCL local LLM path was operational.

Symptoms:

- PTT intermittently fails with `STT returned empty transcript`.
- PTT listening does not stay open long enough for the user to finish speaking.
- STT misrecognized a United States capital question as `edsie what is the capitol`, producing an answer for Poland.

Evidence from code pass:

- Desktop PTT invokes the resident backend endpoint `/session/ptt`; it does not stream WebView audio.
- `ResidentVoiceInvocationService` uses `voice_service.capture_audio(duration_s=3.0)` for PTT when no audio is supplied, so PTT is a fixed three-second backend capture window.
- `capture_audio()` uses `sounddevice.rec(...)` at 16 kHz and waits for completion; there is no voice activity detection, click-to-stop, or press-and-hold capture boundary in this path.
- Empty transcript is produced when `TurnEngine.run_voice_turn()` receives blank STT output and returns `STT returned empty transcript`.
- Current ARM64 STT readiness selects `qnn`, which resolves to `QnnWhisperRuntime`.
- `QnnWhisperRuntime` uses `openai/whisper-base` preprocessing/tokenizer pieces but starts decode from only `<|startoftranscript|>` and does not appear to force English transcription tokens or task/language prompts.

Likely problem areas:

- PTT UX/control contract: the button reports listening, but backend capture is fixed-duration and may not align with actual speech start/end.
- Audio ingress diagnostics: empty transcripts need RMS/peak/duration/input-device evidence surfaced near the failure.
- QNN Whisper decode prompt: language/task control should be audited for English transcription stability.
- Wake monitor and PTT microphone contention should be checked, since wake monitoring remains active and uses the microphone path around PTT invocations.

Post-slice follow-up target:

Design a real PTT capture contract for desktop use, then validate it with live microphone tests on Windows ARM64 before tuning QNN Whisper decode behavior.
