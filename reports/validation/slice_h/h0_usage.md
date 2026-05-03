# Slice H.0 Local Cross-Host Evidence Usage Note

## Purpose
- Collect H.0 cross-host evidence for Slice H voice acceleration viability.
- This is a temporary local validation artifact only.
- Durable closeout summary belongs in `CHANGE_LOG.md` after proof.

## File naming
- `reports/validation/slice_h/h0-x64.md`
- `reports/validation/slice_h/h0-arm64.md`
- Optional Advisor/User synthesis: `reports/validation/slice_h/h0-combined.md`

## Per-host report template
```md
# H.0 Evidence Report — <x64|arm64>

- Commit: `<git-hash>`
- Host class: `<Windows x64|Windows ARM64>`
- Timestamp: `<YYYY-MM-DD HH:MM TZ>`

## Commands run
- `backend/.venv/Scripts/python scripts/validate_backend.py profile`
- `<additional read-only command(s) if used>`

## Profile / preflight summary
- Capability/profile summary: `<brief observed summary>`
- Key preflight tokens observed:
  - `ep:QNNExecutionProvider: <present|missing>`
  - `ep:CUDAExecutionProvider: <present|missing>`
  - `ep:DmlExecutionProvider: <present|missing>`
  - `dll:QnnHtp: <present|missing>`
  - `QAIRT_SDK_PATH: <set|unset>`

## STT device findings
- CPU: `<PASS|SKIP-no-host|SKIP-prereq-missing|Deferred|Degraded-memory-constrained>` — `<note>`
- CUDA: `<...>` — `<note>`
- QNN: `<...>` — `<note>`
- DirectML: `<...>` — `<note>`

## TTS device findings
- CPU: `<PASS|SKIP-no-host|SKIP-prereq-missing|Deferred|Degraded-memory-constrained>` — `<note>`
- CUDA: `<...>` — `<note>`
- QNN: `<...>` — `<note>`
- DirectML: `<...>` — `<note>`

## Model / artifact findings
- STT model artifacts: `<observed paths/status>`
- TTS model artifacts: `<observed paths/status>`
- Quantized artifacts (if any): `<observed paths/status>`

## H.0 close-state table
| Path | State | Notes |
|---|---|---|
| STT-CPU | `<PASS|SKIP-no-host|SKIP-prereq-missing|Deferred|Degraded-memory-constrained>` | `<note>` |
| STT-CUDA | `<...>` | `<note>` |
| STT-QNN | `<...>` | `<note>` |
| STT-DirectML | `<...>` | `<note>` |
| TTS-CPU | `<...>` | `<note>` |
| TTS-CUDA | `<...>` | `<note>` |
| TTS-QNN | `<...>` | `<note>` |
| TTS-DirectML | `<...>` | `<note>` |

## Blockers / skips
- `<blocker or skip reason(s)>`

## Minimal raw excerpts
```text
<paste only minimal lines needed from profile/preflight output>
```
```

## Rules
- Each host updates only its own host report file.
- Do not commit generated H.0 report files.
- Do not add new `.gitignore` rules unless current repo truth proves `/reports/validation/` is not ignored.
- Keep raw excerpts minimal.
- Do not run H.0 validation yet.
- Do not modify `20260505-slice_h.md`, `slices.md`, `CHANGE_LOG.md`, or `SYSTEM_INVENTORY.md`.
