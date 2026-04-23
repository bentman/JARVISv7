# AGENTS.md: Agent Operating Contract for JARVISv7

This file is the authoritative operating contract for all AI and human agents working in this repository. It is loaded before every session. Keep it current; stale rules actively mislead.

## 1. Highest Priority Rule: Python Environment Isolation

- All Python commands must use `backend/.venv`.
- Never use global Python packages for this project.
- Never install Python dependencies globally.
- All Python commands run from the **repo root** (where `pyproject.toml` lives). The virtual environment lives at `backend/.venv/` but the package metadata is at the repo root.

Dependency source of truth:

- `pyproject.toml` (at repo root) is the single source of truth for all Python dependencies and extras.
- `backend/requirements.txt` is a **generated lockfile** of the base extra, emitted by `scripts/provision.py lock` for CI consumers. Never edit it by hand.
- Hardware-family packages are declared as extras in `pyproject.toml` under `[project.optional-dependencies]`. They are resolved and installed by the provisioning script, never by hand.
- If a new package is required for an approved code change, declare it in the proposal. Add it to the correct extra in `pyproject.toml` (base `[project].dependencies` for universal packages, or a named hardware extra for hardware-family packages) and re-provision before implementing code that depends on it.
- Default version operator is `>=`. Use `==` only with a strong, documented reason.
- No runtime-specific ML package belongs in base dependencies. ML packages enter through hardware extras only.

Provisioning authority:

- `scripts/provision.py` is the **only** entry point for installing Python dependencies. It reads the current hardware profile, resolves the correct extras, and composes the `pip install -e '.[...]'` invocation against the repo-root `pyproject.toml`.
- To provision a new host: `backend/.venv/Scripts/python scripts/provision.py install`
- To verify without installing: `backend/.venv/Scripts/python scripts/provision.py verify`
- To regenerate the lockfile: `backend/.venv/Scripts/python scripts/provision.py lock`
- To see why each extra was chosen: `backend/.venv/Scripts/python scripts/provision.py explain`
- Never run `pip install` or `pip install -r ...` directly; always go through the provisioning script.

Required command pattern (Windows PowerShell, run from repo root):

- `backend/.venv/Scripts/python <command>`

First-time setup (run from repo root; executed in order by `scripts/bootstrap.py`):

1. Create the virtual environment: `python -m venv backend/.venv`
2. Upgrade pip inside the venv: `backend/.venv/Scripts/python -m pip install --upgrade pip`
3. Install via the provisioning script (reads repo-root `pyproject.toml`, resolves extras from current host profile):
   `backend/.venv/Scripts/python scripts/provision.py install`

Prefer `scripts/bootstrap.py` for new-host setup; it enforces the full sequence (profile → provision → ensure models → preflight → readiness) with checkpoints.

If `backend/.venv` is broken or inconsistent, stop and report minimal repair steps before continuing.

## 2. Core Operating Constraints

- Do not guess. If something cannot be verified from repository evidence, state what was checked and stop.
- Do not claim completion without reproducible evidence.
- Do not expand scope beyond the explicit request.
- Do not create new repo artifacts unless explicitly requested.
- Do not introduce parallel architectures, shadow systems, or alternate workflows.
- Prefer existing repository patterns and minimal diffs.
- Keep output concise and evidence-focused.

Programming principles (non-negotiable):

- Reinforce existing patterns: before adding new structure, reuse existing repository patterns for file placement, naming, command flow, and validation approach. If no pattern exists, propose the smallest consistent extension.
- Test-Configure-Install: for dependency or runtime setup, test if present, configure if exists, install if missing. For updates, always reconfigure and re-validate.
- KISS: keep implementations simple, direct, and easy to follow.
- Idempotency: commands and changes must be safe to re-run without unintended side effects.
- DRY: reuse shared logic and existing utilities; avoid duplicating logic.
- YAGNI: add only what is required for the current approved scope.
- Separation of concerns: each module or change addresses one responsibility.
- Deterministic operations: prioritize efficient, repeatable, and deterministic command sequences and outcomes.

## 3. Hardware Architecture Awareness

JARVISv7 supports multiple host classes (Windows x64, Windows ARM64 at minimum). All work must respect this:

- **No runtime file may contain host-detection logic.** `backend/app/hardware/profiler.py` is the sole source of hardware facts. `backend/app/hardware/provisioning.py` is the sole source of extras resolution.
- **No DLL or backend-path bootstrap outside `backend/app/hardware/preflight.py`.** No runtime file calls `os.add_dll_directory` or equivalent.
- **Every voice-family runtime accepts `device` as a constructor parameter.** Adding a new device value is a branch inside an existing runtime, never a new file.
- When proposing changes, state which host classes are affected and which are unaffected.
- When reporting validation, state which host class the evidence was collected on.

## 4. Deterministic Execution Rules

- Execution must be deterministic and approval-gated.
- Use explicit, reproducible command sequences.
- Prefer non-interactive command flags and explicit paths to keep runs reproducible.
- Use smallest viable validation first, then broaden only when required.
- If repeated attempts do not change failure mode, stop and report.
- Do not silently iterate after failed validation.

## 5. Approval-Gated Change Control

Before editing, provide a short proposal and wait for explicit approval when work touches any of the following:

- Multiple files
- Core backend systems (hardware, conversation, cognition, routing, services, agents)
- Tests or validation harnesses
- Scripts (provisioning, bootstrap, validation, proving host)
- Desktop shell (`desktop/`)
- Docker/compose surfaces
- Dependency changes (`pyproject.toml` extras)
- Environment repair steps
- `pyproject.toml` metadata or tooling config

Proposal format:

- Files to modify
- Host classes affected
- Commands to run
- Expected evidence

Then stop until approved.

## 6. Authoritative Truth Sources

Use this precedence order:

1. `AGENTS.md` (this file)
2. `ProjectVision.md`
3. `slices.md`
4. `repo_tree.md`
5. `SYSTEM_INVENTORY.md`
6. `CHANGE_LOG.md`

If a conflict is observed between files and runtime behavior, report the conflict and propose the smallest correction.

## 7. Scripts

All scripts live in `scripts/`. They are orchestrators over `backend/app/**` and never duplicate application logic.

Shared CLI convention — every script in `scripts/`:
- Accepts `--verbose`, `--dry-run`, `--trace-to <dir>`.
- Emits a **host-fingerprint line** as its first stdout: arch, Python version, active extras, readiness summary.

Key scripts and their roles:

- `scripts/bootstrap.py` — end-to-end new-host setup: profile → provision → ensure models → preflight → readiness summary. Enforces checkpoints in order; first failure halts with a clear reason.
- `scripts/provision.py` — **sole provisioning authority**. Subcommands: `install`, `verify`, `lock`, `dry-run`, `explain`.
- `scripts/ensure_models.py` — model catalog acquisition / verification.
- `scripts/run_backend.py` — start backend API only (no desktop shell).
- `scripts/run_jarvis.py` — proving host (developer/diagnostic tool). **Not the durable application surface.** `desktop/` is the durable surface.
- `scripts/validate_backend.py` — **sole validation authority**. Subcommand-based; see Section 8.

## 8. Validation Requirements

General:

- Validation must test observable behavior.
- Include exact command(s) and outcome (`PASS`, `FAIL`, `SKIPPED`, or equivalent).
- Include a minimal output excerpt needed to prove the claim.
- State which host class the validation was run on.
- Validation evidence should confirm repeatability for deterministic operations.

Backend validation via `scripts/validate_backend.py`:

- Subcommands:
  - `profile` — run profiler + preflight; print capability report.
  - `unit` — unit suite.
  - `integration` — integration suite.
  - `runtime [--families stt,tts,llm,wake] [--devices cpu,cuda,directml,qnn]` — live runtime suite, marker-filtered.
  - `regression` — minimum green-on-current-host set that every slice closeout must pass.
  - `matrix` — acceleration matrix (Group B gate).
  - `all` — unit + integration + regression.
  - `ci` — suppresses `live` markers; missing hardware = skipped-ok.
- Exit codes: `0` pass, `1` fail, `2` skipped-not-failed, `3` environment-unsatisfied.
- Always use the validator for slice closeout evidence; raw pytest is acceptable for developer inner loops but is not evidence for governance docs.

Test architecture:

- Tests are **marker-gated, not directory-split by arch**. Pytest markers: `x64`, `arm64`, `cuda`, `directml`, `qnn`, `live`, `slow`, `requires_ollama`, `requires_redis`, `requires_searxng`, `requires_docker`, `stt`, `tts`, `llm`, `wake`, `turn`, `desktop`, `agents`.
- `backend/tests/conftest.py` exposes `skip_unless_*` helpers that read from the profiler + preflight.
- Directory structure reflects test purpose and functional domain, not host class:
  - `backend/tests/unit/` — fast, no hardware, no network.
  - `backend/tests/integration/` — multi-module, no live hardware.
  - `backend/tests/runtime/` — live hardware (marker-gated).
- Coverage expectation: backend `*.py` files should have pytest coverage; minimum import/structure, preferably behavior.

Frontend / Desktop:

- Use existing project-defined commands and runtime surfaces.
- Do not invent alternate tooling paths.

Warnings:

- Treat warnings as backlog unless they break correctness, safety, or required behavior.

## 9. Task Execution Workflow

Apply Section 2 programming principles at each step.

For each task:

1. Discover: identify smallest relevant file set and validation path.
2. Confirm scope, constraints, and affected host classes.
3. Propose when required by Section 5.
4. Implement only approved changes.
5. Validate with explicit commands via Section 8 pattern.
6. Report exact outcomes with minimal proof including host class.
7. Stop when objective is complete.

Python test expectation:

- Add or maintain a standard `pytest` test for almost every backend `*.py` module.
- Place tests under `backend/tests/unit/`, `backend/tests/integration/`, or `backend/tests/runtime/` as appropriate.
- Apply appropriate arch/device markers per test.
- For scoped tasks, required tests apply to changed/affected modules; broad backfill is separate scope unless explicitly requested.
- Minimum bar: import/structure validation.
- Preferred bar: behavior/function validation.

Do not add follow-up work unless explicitly requested.

## 10. File and Artifact Boundaries

- Keep runtime artifacts out of repository root.
- Use existing project locations for generated data (`data/`, `cache/`, `reports/`, `models/`).
- Do not introduce new storage locations without explicit approval.
- Ensure `.gitignore` rules cover generated artifacts when changes require it.
- `backend/requirements.txt` is generated, not hand-edited.
- `config/hardware/notes.md` holds human-readable operator prerequisites only; package sets live in `pyproject.toml`.
- Model artifacts live in `models/`; never in `backend/` or `config/`.

## 11. CHANGE_LOG.md Requirements

`CHANGE_LOG.md` is append-only and records completed, verified work.

Rules:

- Never rewrite or delete prior entries.
- Maintain entries in descending chronological order (newest first).
- Add new entries directly under `## Entries`.
- Log only after validation evidence exists.
- Use factual, past-tense statements.
- If prior record is inaccurate, append a corrective entry; do not edit history.

Minimum entry content:

- Timestamp
- Short summary of what changed
- Scope (files/areas)
- Host class(es) validated on
- Evidence (exact command(s) run + minimal excerpt pointer or excerpt)

## 12. SYSTEM_INVENTORY.md Requirements

`SYSTEM_INVENTORY.md` is the capability truth ledger.

Rules:

- Record only observable repository artifacts (files, directories, executable code, configuration, scripts, explicit UI text).
- Do not include intent, plans, or inferred behavior.
- One component entry equals one observed capability/feature.
- New capabilities must be added at the top under `## Inventory` and above `## Observed Initial Inventory`.
- Corrections and clarifications must be added only below `## Appendix`.
- Required entry fields:
  - Capability: brief descriptive component name with date/time
  - State: `Planned`, `Implemented`, `Verified`, `Deferred`
  - Location: relative file path(s)
  - Validation: method and/or relative script path(s); include host class
  - Notes: optional, one line max
- Do not promote state without validation evidence.

## 13. Git Safety Rules

Never run destructive git operations without explicit approval, including:

- `git restore`
- `git reset`
- `git clean`
- `git rebase`
- history rewrites

If rollback is requested, propose the safest approach based on whether changes are committed or uncommitted.

## 14. Reporting Format for Agent Responses

When reporting completion or progress, use:

- Summary
- Host class validated on
- Files inspected and changed
- Commands executed and outcomes
- Minimal evidence excerpt
- Stop (unless next action is explicitly requested)

Do not state or imply verification without corresponding command evidence.
