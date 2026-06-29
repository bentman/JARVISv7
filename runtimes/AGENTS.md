# runtimes/AGENTS.md

Applies to `runtimes/**`. The root contract still applies.

## Purpose

`runtimes/` stores local runtime sidecars used by catalog/runtime profiles. It is not application source code.

Keep boundaries clear:

- model artifacts belong in `models/`
- backend adapters belong in `backend/app/runtimes/`
- runtime sidecar files belong here only when explicitly staged
- third-party build trees stay outside the repo

Generated sidecar payloads are normally local artifacts and must not be committed unless the task explicitly requires it.

## Layout

Keep folder names aligned with catalog/profile metadata. Do not create new sidecar paths without updating the relevant config and validation path.

Known llama.cpp sidecar path pattern:

- `runtimes/llama.cpp/<host-profile>/`

A sidecar folder should contain only required runtime files plus approved provenance when useful.

## Build and staging

Use existing helper docs/scripts when available:

- `docs/jarvis-arm-llamacpp.md`
- `docs/jarvis-arm-llamacpp.ps1`

Do not commit build folders, package caches, temporary archives, or host-local absolute paths.

Do not replace a known-good sidecar in place without approval. Prefer side-by-side staging or a reversible plan.

## Validation

Presence is not proof. Verify sidecars through repo commands.

Common checks:

- `backend/.venv/Scripts/python scripts/ensure_models.py --family llm --model assistant-small-q4 --verify-only`
- `backend/.venv/Scripts/python scripts/validate_backend.py profile`

For accelerator sidecars, live proof must show the expected accelerator in readiness output, runtime logs, or focused live tests. If accelerator proof is missing, report staged/degraded rather than verified.

If a sidecar is missing, fix acquisition/staging or report the missing artifact. Do not patch backend code to hide it.
