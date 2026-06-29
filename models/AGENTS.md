# models/AGENTS.md

Applies to `models/**`. The root contract still applies.

## Model artifact boundary

`models/` holds local model artifacts. It is not a source-code location and not a configuration authority.

Catalog/config metadata lives under `config/models/`. Runtime code consumes catalog metadata; it must not infer model identity from ad hoc filesystem guesses when a catalog entry exists.

Do not commit large model artifacts unless explicitly requested. Most model files are local acquisition/staging outputs and should remain ignored.

## Acquisition and verification

Use `scripts/ensure_models.py` for configured model acquisition and verification.

Common checks:

- `backend/.venv/Scripts/python scripts/ensure_models.py --verify-only`
- `backend/.venv/Scripts/python scripts/ensure_models.py --family stt --model <name> --verify-only`
- `backend/.venv/Scripts/python scripts/ensure_models.py --family llm --model <name> --verify-only`

Do not manually download, rename, or reshuffle model files unless the task explicitly calls for staging a known artifact.

## Layout and naming

Respect existing family folders:

- `models/stt/`
- `models/tts/`
- `models/wake/`
- `models/llm/`

Model folder names must match the catalog model id unless an approved migration says otherwise:

- `models/<family>/<model-id>/`

Use side-by-side staging for new model variants. Do not replace an existing model in place when the approved work calls for a new catalog identity.

For multi-part models, keep stable component names from the catalog or source manifest. Acceptable generic component folders include:

- `encoder/`
- `decoder/`
- `tokenizer/`
- `provenance/`

Do not create model-specific naming schemes inside `models/` unless the catalog/config design requires them.

## Provenance

When a local artifact is staged manually, record enough provenance to reproduce or audit it:

- source package or repo
- model id or artifact id when applicable
- date/time of acquisition
- host class used for validation
- verification command and outcome

Use `provenance/manifest.json` when provenance is stored beside a model.

Do not commit tokens, account-specific metadata, absolute private paths, or downloaded credentials.

## Validation

Model readiness is not runtime proof. Pair model verification with runtime/profile validation when claiming a model works.

Report missing artifacts as degraded/missing state. Do not patch runtime code to hide missing model files.
