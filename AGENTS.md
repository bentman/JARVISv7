# AGENTS.md: Repository Operating Contract for JARVISv7

This is the repo-wide operating contract for AI and human agents. It is intentionally compact. Follow the nearest `AGENTS.md` for files in a subtree; explicit user/developer instructions override repository instructions. If instructions conflict, report the conflict and use the narrowest safe path.

## 1. Precedence and truth sources

Use this order for repository truth:

1. Explicit user/developer instruction for the current task
2. Nearest scoped `AGENTS.md`
3. This root `AGENTS.md`
4. `ProjectVision.md`
5. `repo_tree.md`
6. `SYSTEM_INVENTORY.md`
7. `CHANGE_LOG.md`

Do not infer completion from intent docs. `SYSTEM_INVENTORY.md` records observable capability state. `CHANGE_LOG.md` records completed work after validation evidence exists.

## 2. Environment contract

Run from the repo root unless a scoped file says otherwise.

Python:

- Use `backend/.venv/Scripts/python` for all repo Python commands.
- Never install Python packages globally.
- `pyproject.toml` is the dependency source of truth.
- `backend/requirements.txt` is generated; never edit it by hand.
- Use `scripts/provision.py` for dependency install/verify/lock/explain.
- Prefer `scripts/bootstrap.py` for new-host setup.

Desktop:

- Use `npm --prefix desktop ...` for desktop commands.
- Do not install Tauri or desktop dependencies globally for this repo.

Generated/runtime data belongs in existing locations only: `data/`, `cache/`, `reports/`, `models/`, or `runtimes/`. Do not invent new storage roots without approval.

## 3. Scope control

Default behavior:

- Do not guess. Verify from repository evidence or state what was checked and stop.
- Do not expand scope beyond the explicit request.
- Do not create new repo artifacts unless requested.
- Do not introduce parallel architectures, shadow workflows, or alternate setup paths.
- Do not create custom helper scripts/docs as a workaround for missing design.
- Prefer existing patterns and minimal diffs.
- Keep responses concise and evidence-focused.

Before editing, provide a short proposal and wait for approval when touching multiple files, core backend systems, scripts, validation harnesses, desktop, Docker/compose, dependencies, environment repair, or repo tooling config.

Proposal format:

- Files to modify
- Host classes affected
- Commands to run
- Expected evidence

## 4. Work pattern

For each task:

1. Discover the smallest relevant file set.
2. Read any scoped `AGENTS.md` that applies.
3. Confirm scope and affected host classes.
4. Propose when required.
5. Implement only approved changes.
6. Validate observable behavior.
7. Report exact outcomes and stop.

Use simple, deterministic steps. For validation and repair, run commands one at a time unless one compound command is required by the toolchain.

## 5. Validation evidence

Do not claim verification without command evidence.

Required report fields for validation claims:

- exact command
- outcome (`PASS`, `FAIL`, `SKIPPED`, or equivalent)
- host class (`windows-amd64`, `windows-arm64`, etc.)
- minimal output excerpt or report path

Use `scripts/validate_backend.py` for backend closeout evidence. Raw `pytest` is acceptable for inner-loop development but is not governance closeout evidence unless explicitly requested.

Key validator commands:

- `profile`
- `unit`
- `integration`
- `runtime --families ... --devices ...`
- `regression`
- `matrix`
- `all`
- `ci`

Exit codes: `0` pass, `1` fail, `2` skipped-not-failed, `3` environment-unsatisfied.

## 6. File, artifact, and ignore boundaries

Honor `.agentignore` as a repository contract for files agents should not read, index, embed, or transmit. Treat matching paths as unavailable unless explicit task instructions and repository policy permit otherwise.

Do not commit generated artifacts unless the task explicitly requires it. Ensure `.gitignore` covers any new generated output. Model artifacts live in `models/`; runtime sidecars live in `runtimes/`; package/dependency metadata lives in `pyproject.toml`.

Artifact/helper docs are maintenance surfaces for approved designs, not design authority. Use existing helpers as documented; do not invent a new helper workflow when config/catalog/runtime design should own the behavior.

Naming conventions for approved helper artifacts:

- docs: `docs/<area>-<purpose>.md`
- PowerShell helper: `docs/<area>-<purpose>.ps1`
- temporary handoff package: `docs/temp/<name>-YYYYMMDDHHMMSS.zip`
- provenance: `provenance/manifest.json`

## 7. CHANGE_LOG and SYSTEM_INVENTORY

`CHANGE_LOG.md` is append-only. Add entries only after validation evidence exists. Never rewrite old entries; append a corrective entry when needed.

`SYSTEM_INVENTORY.md` is the capability truth ledger. Record only observable artifacts and verified/implemented states. Do not promote capability state without evidence. Corrections belong under its appendix unless the file's own instructions say otherwise.

## 8. Git safety

Never run destructive Git operations without explicit approval, including:

- `git restore`
- `git reset`
- `git clean`
- `git rebase`
- history rewrites

If rollback is requested, propose the safest path based on whether the target changes are committed or uncommitted.

## 9. Where to look

Scoped operating files:

- `backend/AGENTS.md` — backend app, tests, runtime selection, hardware rules
- `desktop/AGENTS.md` — Tauri desktop shell rules
- `models/AGENTS.md` — local model artifact rules
- `runtimes/AGENTS.md` — local runtime sidecar rules
- `scripts/AGENTS.md` — repository script conventions

Operational docs:

- `docs/QuickStart.md` — setup and normal commands

Do not treat archived docs, completed slice notes, or helper notes as permission to bypass current source/config/catalog design.

## 10. Reporting format

When reporting completion or progress, use:

- Summary
- Host class validated on
- Files inspected and changed
- Commands executed and outcomes
- Minimal evidence excerpt or report path
- Stop unless a next action was explicitly requested
