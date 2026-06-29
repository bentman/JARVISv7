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

## Layout and naming

Keep folder names aligned with catalog/profile metadata. Do not create new sidecar paths without updating the relevant config and validation path.

Runtime sidecar path convention:

- `runtimes/<runtime-family>/<host-profile>/`

Examples of naming shape only:

- `runtimes/llama.cpp/windows-amd64-cpu/`
- `runtimes/llama.cpp/windows-arm64-cpu/`

A sidecar folder should contain only required runtime files plus approved provenance when useful.

Do not add new sidecar folders, helper docs, or staging scripts unless the catalog/profile/config design already requires them or the task explicitly approves that design change.

## Build and staging

Use existing repository-approved acquisition/staging commands when available. If no designed path exists, stop and propose the missing catalog/profile/config change instead of creating a new workflow.

Do not commit build folders, package caches, temporary archives, or host-local absolute paths.

Do not replace a known-good sidecar in place without approval. Prefer side-by-side staging or a reversible plan.

## Validation

Presence is not proof. Verify sidecars through repo commands.

Common checks:

- `backend/.venv/Scripts/python scripts/ensure_models.py --family llm --model <model-id> --verify-only`
- `backend/.venv/Scripts/python scripts/validate_backend.py profile`

For accelerator sidecars, live proof must show the expected accelerator in readiness output, runtime logs, or focused live tests. If accelerator proof is missing, report staged/degraded rather than verified.

If a sidecar is missing, use the designed acquisition/staging path or report the missing artifact. Do not change backend code only to mask a missing file.
