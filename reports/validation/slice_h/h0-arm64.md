# H.0 Evidence Report — arm64

- Commit: `ce0263a05711e66060fce2e4da0f010b253ee980`
- Host class: `Windows ARM64`
- Timestamp: `2026-05-03 16:15 America/Chicago (UTC-5)`

## Commands run
- `backend\.venv\Scripts\python scripts\validate_backend.py profile`
- `backend\.venv\Scripts\python scripts\validate_backend.py regression`

## Profile / preflight summary
- Arch: `arm64`
- Python version: `3.12.10`
- Provisioned extras: `[hw-cpu-base, hw-arm64-base, hw-npu-qualcomm-qnn, dev]`
- Readiness state: `ready`
- Key preflight tokens observed:
  - `ep:QNNExecutionProvider`: missing (`ep:QNNExecutionProvider:MISSING`)
  - `ep:CUDAExecutionProvider`: missing
  - `ep:DmlExecutionProvider`: missing
  - `dll:QnnHtp`: missing (`dll:QnnHtp:MISSING`)
  - `QAIRT_SDK_PATH`: not reported/set in captured profile output
- DLL/provider discovery notes from profile:
  - `dll_discovery_log`: `[]`
  - Providers listed in tokens: `ep:AzureExecutionProvider`, `ep:CPUExecutionProvider`

## STT device findings (arm64)
- CPU: `PASS` — CPU execution provider token present (`ep:CPUExecutionProvider`).
- CUDA: `SKIP-no-host` — ARM64 Qualcomm host; CUDA/NVIDIA path not present in captured profile.
- QNN: `SKIP-prereq-missing` — `ep:QNNExecutionProvider` and `dll:QnnHtp` not observed in captured profile tokens.
- DirectML: `SKIP-prereq-missing` — DirectML EP token not present in captured profile tokens.

## TTS device findings (arm64)
- CPU: `PASS` — CPU execution provider token present and readiness is `ready`.
- CUDA: `SKIP-no-host` — ARM64 Qualcomm host; CUDA/NVIDIA path not present in captured profile.
- QNN: `SKIP-prereq-missing` — `ep:QNNExecutionProvider` and `dll:QnnHtp` not observed in captured profile tokens.
- DirectML: `SKIP-prereq-missing` — DirectML EP token not present in captured profile tokens.

## Model / artifact findings
- Captured profile/regression output did not enumerate model artifact paths.
- No model export/download/mutation performed in this evidence write-up.

## H.0 close-state table
| Path | State | Notes |
|---|---|---|
| STT-CPU | `PASS` | `ep:CPUExecutionProvider` present |
| STT-CUDA | `SKIP-no-host` | ARM64 Qualcomm host; CUDA/NVIDIA path absent in captured profile |
| STT-QNN | `SKIP-prereq-missing` | `ep:QNNExecutionProvider` and `dll:QnnHtp` not observed |
| STT-DirectML | `SKIP-prereq-missing` | `ep:DmlExecutionProvider` not observed |
| TTS-CPU | `PASS` | CPU EP present; readiness `ready` |
| TTS-CUDA | `SKIP-no-host` | ARM64 Qualcomm host; CUDA/NVIDIA path absent in captured profile |
| TTS-QNN | `SKIP-prereq-missing` | `ep:QNNExecutionProvider` and `dll:QnnHtp` not observed |
| TTS-DirectML | `SKIP-prereq-missing` | `ep:DmlExecutionProvider` not observed |

## Regression evidence
- Command: `backend\.venv\Scripts\python scripts\validate_backend.py regression`
- Result: `PASS`
- Test count: `96 passed`

## Minimal raw excerpts
```text
git rev-parse HEAD
ce0263a05711e66060fce2e4da0f010b253ee980

[fingerprint] arch=arm64 python=3.12.10 extras=[hw-cpu-base,hw-arm64-base,hw-npu-qualcomm-qnn,dev] readiness=ready; tokens=15 profiled=2026-04-27T15:26:20Z
preflight.tokens: ... ep:AzureExecutionProvider, ep:CPUExecutionProvider, import:onnxruntime-qnn, ep:QNNExecutionProvider:MISSING, dll:QnnHtp:MISSING
preflight.dll_discovery_log: []

VALIDATION SUMMARY
[INVARIANTS]
UNIT=PASS
[PASS] JARVISv7 backend regression is validated!
96 passed in 0.23s
```