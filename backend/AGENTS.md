# backend/AGENTS.md

Applies to `backend/**`. The root contract still applies.

## Backend authority boundaries

Backend code owns application behavior. Do not move orchestration into scripts, desktop code, model folders, or runtime artifact folders.

Hardware authority:

- `backend/app/hardware/profiler.py` is the source of hardware facts.
- `backend/app/hardware/provisioning.py` resolves hardware extras.
- `backend/app/hardware/preflight.py` owns DLL/provider/bootstrap probes.
- Runtime modules must not call `os.add_dll_directory` or invent host policy locally.
- Runtime selection consumes profile/preflight/readiness evidence.

Voice/runtime family rule:

- STT, TTS, LLM, and wake runtimes accept device/profile decisions as inputs.
- Add device branches inside existing runtime families when possible.
- Do not create parallel runtime families just to express hardware differences.

## Application structure

Use existing backend layer boundaries:

- `api/` exposes routes and schemas; it should not own runtime policy.
- `conversation/` owns turn/session state flow.
- `cognition/` owns prompt assembly and policy-facing cognition helpers.
- `services/` owns operational services around runtimes and app lifecycle.
- `runtimes/` owns concrete STT/TTS/LLM/wake execution adapters.
- `agents/` remains explicit, policy-gated, and truthful about disabled or dry-run behavior.

Do not hide durable behavior in prompts, route handlers, UI glue, or test fixtures.

## Dependency rules

Backend dependency changes go through `pyproject.toml` and `scripts/provision.py`. No direct `pip install` evidence is acceptable for repository state.

No runtime-specific ML package belongs in base dependencies. Hardware/runtime packages enter the appropriate optional extra.

## Tests

Backend tests live under:

- `backend/tests/unit/`
- `backend/tests/integration/`
- `backend/tests/runtime/`

Tests are marker-gated, not directory-split by architecture. Use existing markers such as `x64`, `arm64`, `cuda`, `directml`, `qnn`, `live`, `stt`, `tts`, `llm`, `wake`, `turn`, `desktop`, and `agents`.

For changed backend modules, add or maintain pytest coverage. Minimum bar is import/structure coverage. Preferred bar is behavior coverage.

Use `backend/tests/conftest.py` helpers for hardware/live skips. Do not implement duplicate host detection inside tests.

## Validation

Inner-loop focused pytest is fine while developing. Closeout evidence must use validator commands unless explicitly waived.

Common backend validation commands:

- `backend/.venv/Scripts/python scripts/validate_backend.py profile`
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration`
- `backend/.venv/Scripts/python scripts/validate_backend.py regression`

For live runtime changes, use `runtime --families ... --devices ...` or the focused live test path required by the slice.

Always report host class with backend validation evidence.
