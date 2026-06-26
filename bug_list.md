# Bug List

## 2026-06-26 - T17 live tests emit sounddevice NumPy 2.5 deprecation warnings

Status: Open

Observed in `C:/Users/bentl/OneDrive/Desktop/T17-LiveTestResults.txt` after the ARM64 T17 operator live run was accepted as PASS with warnings.

Warning census:

- Resident audio activation/live voice command: `3 passed, 376 warnings in 32.29s`.
- Barge-in live command: `1 passed, 242 warnings in 11.13s`.
- Hands-free live command: `1 passed, 270 warnings in 16.91s`.
- Desktop resident voice live command: `1 passed in 35.69s` with no pytest warning summary in the captured output.
- Total captured pytest deprecation warnings: 888, all attributed to `backend\.venv\Lib\site-packages\sounddevice.py:2794`.
- Non-pytest warning text also appeared before each live command: `[transformers] PyTorch was not found. Models won't be available and only tokenizers, configuration and file/data utilities can be used.`

Probable root cause:

- The repeated pytest warnings are third-party `sounddevice` warnings triggered by live microphone reads under installed `numpy=2.5.0` and `sounddevice=0.5.5`.
- The warning text says `sounddevice.py` assigns `data.shape = -1, channels`, which NumPy 2.5 deprecates. Repo code already reshapes captured arrays with `np.asarray(...).reshape(-1)` after reads; the warning is emitted before repo-owned reshaping.
- The warnings correlate with live microphone paths using `sounddevice.InputStream.read()` through `ResidentAudioStream` and wake/voice capture paths, not with deterministic unit/static tests.
- The Transformers/PyTorch text is likely environment/readiness noise from tokenizer/config-only imports on the ARM64 QNN profile, not a failing condition for these accepted live tests.

Possible solution:

- Prefer an upstream dependency fix: upgrade to a `sounddevice` release that is compatible with NumPy 2.5 shape-assignment deprecations once available, through `pyproject.toml` plus `scripts/provision.py` only.
- If no compatible release exists, evaluate a temporary NumPy upper bound below 2.5 for affected host extras, but only after checking ARM64/QNN package compatibility and revalidating voice/runtime paths.
- Avoid blanket warning suppression as the first fix. If suppression is needed temporarily, scope it narrowly to the known `sounddevice.py` NumPy shape deprecation in operator live tests so new audio warnings remain visible.
- Treat the Transformers/PyTorch line separately: confirm whether QNN/STT runtime imports require only tokenizer/config utilities, then either leave as benign readiness noise or route the import through an existing readiness/degraded-status surface.

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
