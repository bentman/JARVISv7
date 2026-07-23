# AGENTS.md: Repository Operating Contract for JARVISv7

This is the repo-wide operating contract for AI and human agents. It is intentionally compact. Follow the nearest `AGENTS.md` for files in a subtree; explicit user/developer instructions override repository instructions. If instructions conflict, report the conflict and use the narrowest safe path.

Keep this file limited to repository-wide rules agents cannot reliably infer from code, docs, or tooling. Put subtree-specific rules in the scoped `AGENTS.md` closest to the affected files.

## 1. Precedence and truth sources

Use this order for repository truth:

1. Explicit user/developer instruction for the current task
2. Nearest scoped `AGENTS.md`
3. This root `AGENTS.md`
4. `ProjectVision.md`
5. `repo_tree.md`
6. `SYSTEM_INVENTORY.md`
7. `CHANGE_LOG.md`

Do not infer completion from intent docs. `SYSTEM_INVENTORY.md` records observable capability state. `CHANGE_LOG.md` records completed work after validation evidence exists. If files conflict with observed behavior, report the conflict and propose the smallest correction.

Before touching config or dependencies:

- `pyproject.toml` is the only source of truth for Python dependencies.
- `backend/requirements.txt` is generated from `pyproject.toml` by `scripts/provision.py lock` for the base extra only. Never hand-edit it.
- Approved dependency changes must go through the correct `pyproject.toml` dependency group or hardware extra, then `scripts/provision.py`; direct `pip install` is not repository evidence.
- `.env` overrides `.env.example` key-by-key. Never edit `.env.example` for local/operator changes; copy it to `.env` and change `.env`.
- `backend/app/core/settings.py` classifies settings through `SETTING_ENV_CLASSIFICATION`.
- Prefer `primary` settings for normal operator changes. Touch `advanced`, `derived`, `services`, `secret`, `compatibility`, or `test-only` settings only when the task requires it.
- Do not add new environment variables, dependency groups, setup paths, or storage roots unless they are the narrowest approved solution.

Python:

- Use `backend/.venv/Scripts/python` for all repo Python commands.
- Never install Python packages globally.
- Use `scripts/provision.py` for dependency install/verify/lock/explain.
- Prefer `scripts/bootstrap.py` for new-host setup.
- Use `>=` by default for dependency versions; use `==` only with a documented reason.
- Keep runtime-specific ML packages out of base dependencies; use hardware extras.
- If `backend/.venv` is broken or inconsistent, stop and report minimal repair steps before continuing.

Desktop:

- Use `npm --prefix desktop ...` for desktop commands.
- Do not install Tauri or desktop dependencies globally for this repo.

Generated/runtime data belongs in existing locations only: `data/`, `cache/`, `reports/`, `models/`, or `runtimes/`. Do not invent new storage roots without approval.

## 3. Scope control and engineering principles

Default behavior:

- Do not guess. Verify from repository evidence or state what was checked and stop.
- Do not claim completion without reproducible evidence.
- Do not expand scope beyond the explicit request.
- Do not create new repo artifacts unless requested.
- Do not introduce parallel architectures, shadow workflows, or alternate setup paths.
- Do not create custom helper scripts/docs as a workaround for missing design.
- Prefer existing patterns and minimal diffs.
- Keep responses concise and evidence-focused.

### GitHub issue authority

Issue templates, labels, parent/child relationships, and dependencies describe work. They do not authorize an agent to create, restructure, merge, or continue into additional work.

The assigned issue is the task boundary. If it is too broad, blocked, or incorrectly structured, report the problem and proposed change, then stop.

Do not create or begin other issues, change workflow rules, merge pull requests, or delete branches unless explicitly requested.

Programming principles:

- Prefer use/re-use/modify existing files/patterns/tests over add/create new. Existing Patterns First: reinforce existing patterns before adding new structure. If no pattern exists, propose the smallest consistent extension.
- KISS: keep implementations simple, direct, and easy to follow. Avoid clever abstractions, unnecessary indirection, and speculative generalization.
- YAGNI: add only what the approved task requires. Do not build future capabilities, alternate modes, or convenience layers unless they are explicitly requested.
- DRY: reuse shared logic and utilities. Avoid duplicating logic, command paths, configuration rules, or validation behavior.
- Single Responsibility: keep each module, function, script, and change focused on one clear responsibility.
- Idempotency: commands and changes must be safe to re-run. Setup and repair flows should test current state before changing it.
- Test-Configure-Install: for setup, test if present, configure if available, install only if missing. For updates, reconfigure and re-validate.
- Determinism: prefer explicit paths, stable ordering, non-interactive flags, and repeatable command sequences.
- Minimal Surface Area: avoid new dependencies, files, services, environment variables, or helper scripts unless they are the narrowest approved solution.
- Observable Behavior: favor changes that can be validated by command output, tests, reports, or visible runtime behavior.

Before editing, provide a short proposal and wait for approval when touching multiple files, core backend systems, scripts, validation harnesses, desktop, Docker/compose, dependencies, environment repair, or repo tooling config.

Proposal format:

- Files to modify
- Host classes affected
- Commands to run
- Expected evidence
- Coverage scope: import/structure for diffs under 20 lines unless new logic branches are introduced; behavior coverage only for new or changed logic branches.

## 4. Work pattern

For each task:

1. Discover the smallest relevant file set.
2. Read any scoped `AGENTS.md` that applies.
3. Confirm scope and affected host classes.
4. Propose when required.
5. Implement only approved changes.
6. Validate observable behavior.
7. Report exact outcomes and stop.

Use simple, deterministic steps. Prefer non-interactive flags and explicit paths. For validation and repair, run commands one at a time unless one compound command is required by the toolchain. Use the smallest viable validation first, then broaden only when required. If repeated attempts do not change the failure mode, stop and report.

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

Exit codes: `0` pass, `1` fail, `2` skipped-not-failed, `3` environment-unsatisfied`.

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

`CHANGE_LOG.md` records completed codebase changes after objective completion and validation evidence. Add new entries only at the top directly under `## Change Entries`. Corrections or clarifications go only below `## Change Appendix`. Do not edit, reorder, or delete past entries.

`SYSTEM_INVENTORY.md` is the observable capability ledger. Record only capability or feature groups observed in repository artifacts. Add new entries only at the top directly under `## Inventory Entries`. Corrections or clarifications go only below `## Inventory Appendix`. Do not promote capability state without evidence.

## 8. Git safety

Never run destructive Git operations without explicit approval, including:

- `git restore`
- `git reset`
- `git clean`
- `git rebase`
- history rewrites
