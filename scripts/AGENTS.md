# scripts/AGENTS.md

Applies to `scripts/**`. The root contract still applies.

## Script role

Scripts are repository operators. They orchestrate backend modules and project commands; they must not become a second application layer.

Keep application logic in `backend/app/**`. If a script needs behavior that belongs to the app, add a backend helper and call it from the script.

## Environment

Run scripts from the repo root with the repo Python:

- `backend/.venv/Scripts/python scripts/<name>.py ...`

Scripts should resolve the repo root from their own file location and avoid relying on the caller's accidental current directory beyond the documented repo-root command pattern.

Do not call global Python, global pip, or unpinned external helper paths.

## CLI conventions

Core operational scripts should support the shared flags when applicable:

- `--verbose`
- `--dry-run`
- `--trace-to <path>`
- `--profile` where host profile output is relevant

Do not add interactive prompts unless the operation is intentionally dangerous or cost-incurring. Prefer explicit flags and explicit paths.

## Side effects

A script must make side effects obvious:

- parse arguments before work starts
- print the planned command or action when useful
- honor `--dry-run` for filesystem/network/install actions when practical
- fail fast on non-zero subprocess exits
- do not silently retry a failure that has not changed

For validation/repair workflows, keep command boundaries clear. Avoid one-line chains that hide which step failed.

## Specific authorities

Current primary script roles:

- `bootstrap.py` — new-host setup checkpoint runner
- `provision.py` — only Python dependency install/verify/lock/explain authority
- `ensure_models.py` — model/runtime artifact acquisition and verification
- `run_backend.py` — backend API launcher
- `run_jarvis.py` — proving-host diagnostic runner, not durable UI
- `validate_backend.py` — validation authority for governance closeout

Do not create alternate setup, provisioning, validation, or runtime launch paths without approval.

## Tests

Script behavior belongs under `backend/tests/unit/scripts/` unless a different existing test pattern clearly applies.

Tests should cover argument parsing, dry-run behavior, failure handling, and emitted status/evidence where relevant.

## Native commands

When invoking native tools, capture/propagate exit codes and make stderr visible. Do not let warnings look like success when the command failed.

For PowerShell helper scripts, avoid native stderr patterns that PowerShell converts into misleading `NativeCommandError` when the underlying command succeeded.

## Validation

For script changes, run the smallest focused script test first, then the relevant validator command. Report host class and exact command outcomes.
