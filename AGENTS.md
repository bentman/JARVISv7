# AGENTS.md - JARVISv7 Agent Operating Contract

JARVISv7 is a local-first, voice-first desktop assistant. The backend owns application behavior, hardware/runtime truth, session and turn flow, memory, and policy; the desktop is a thin Tauri surface over backend APIs.

This is the repo-wide operating contract for AI and human agents. Keep it short, concrete, and limited to rules that are hard to infer from code, docs, or tooling. The nearest `AGENTS.md` controls a subtree; current user/developer instructions override repo guidance. If instructions conflict, report the conflict and use the narrowest safe path.

## Start with the right sources

Use repository truth in this order:

1. Current user/developer instruction
2. Nearest scoped `AGENTS.md`
3. This root `AGENTS.md`
4. `ProjectVision.md`
5. Accepted ADRs in `docs/adr/`
6. `repo_tree.md`

Do not infer completion from intent docs. Record completed work only after validation evidence exists. If docs and behavior conflict, report it and propose the smallest correction.

## Before changing config or dependencies

- `pyproject.toml` is the only source of truth for Python dependencies.
- `backend/requirements.txt` is generated from `pyproject.toml` by `scripts/provision.py lock` for the base extra only; do not hand-edit it.
- Approved dependency changes go through the right `pyproject.toml` group or hardware extra, then `scripts/provision.py`.
- Direct `pip install` is not allowed and is not repo evidence.
- Use `>=` for dependency versions by default; use `==` only with a documented reason to pin a version.
- Keep runtime-specific ML packages out of base dependencies; use hardware extras.
- `.env` overrides `.env.example` key-by-key. Do not edit `.env.example` for local/operator changes; copy it to `.env` and change `.env`.
- `backend/app/core/settings.py` classifies settings through `SETTING_ENV_CLASSIFICATION`.
- Prefer `primary` settings for normal operator changes. Touch `advanced`, `derived`, `services`, `secret`, `compatibility`, or `test-only` only when required.
- Add environment variables, dependency groups, setup paths, or storage roots only when they are the narrowest approved solution.

## Use repo tools

- Python commands use (infer appropriate pwsh or posix behaviors)
  - Windows: `.\backend\.venv\Scripts\python`
  - Linux: `backend/.venv/bin/python`
- Do not install Python packages globally.
- Use `scripts/bootstrap.py` for new-host setup.
- Use `scripts/provision.py` for dependency install, verify, lock, and explain.
- If `backend/.venv` is broken or inconsistent, stop and report minimal repair steps before continuing.
- Desktop commands use `npm --prefix desktop ...`.
- Do not install Tauri or desktop dependencies globally for this repo.
- Generated/runtime data belongs only in existing roots: `data/`, `cache/`, `reports/`, `models/`, or `runtimes/`.

## Work in the order an agent should encounter it

1. Discover the smallest relevant file set.
2. Read any scoped `AGENTS.md` that applies.
3. Confirm the affected host class, module, and contract.
4. Propose first when the change affects dependencies, config, storage, setup, architecture, runtime behavior, or validation scope.
5. Implement only the approved or directly requested change.
6. Validate the changed behavior with the smallest useful command.
7. Report exact outcomes and stop.

Use deterministic, non-interactive commands with explicit paths. Prefer existing files, patterns, helpers, and tests. Avoid parallel architectures, shadow workflows, alternate setup paths, custom helper scripts, or new docs unless explicitly required.

## Engineering principles

- KISS: keep changes simple, direct, and readable.
- YAGNI: do not build future capability, alternate modes, or convenience layers.
- DRY: reuse shared logic, command paths, config rules, and validation behavior.
- Idempotency: setup and repair flows test current state before changing it and are safe to rerun.
- Determinism: prefer stable ordering, explicit paths, fixed inputs, and repeatable command sequences.
- Minimal surface area: avoid new dependencies, services, settings, files, and storage roots unless they are the smallest correct solution.
- Test-configure-install: test if present, configure if available, install only if missing.
- Observable behavior: prove changes with command output, reports, tests, or visible runtime behavior.

## Validation and testing

Do not claim verification without command evidence. Report validation with:

- exact command
- outcome: `PASS`, `FAIL`, `SKIPPED`, or equivalent
- host class, such as `windows-amd64`, `windows-arm64`, `linux-amd64`, `linux-arm64`, etc.
- minimal output excerpt or report path

Use `scripts/validate_backend.py` for backend closeout evidence. Raw `pytest` is acceptable for inner-loop development, but it is not governance closeout evidence unless explicitly requested.

Key validator commands: `profile`, `unit`, `integration`, `runtime --families ... --devices ...`, `regression`, `matrix`, `all`, `ci`. Exit codes: `0` pass, `1` fail, `2` skipped-not-failed, `3` environment-unsatisfied.

Testing exists to falsify changed behavior, not to justify activity. Test count is not a completion metric.

- Search the existing suite before adding tests.
- Prefer reuse, extension, parameterization, reformatting, or consolidation of the nearest existing test.
- Add a new test only when a distinct changed contract, branch, regression, integration boundary, or failure mode cannot fit in existing tests.
- Do not duplicate the same assertion across unit, integration, runtime, and E2E layers unless each layer protects a distinct risk.
- Prefer behavior and contract assertions over implementation-detail assertions.
- Do not change production structure solely to accommodate redundant tests.
- Run the smallest viable validation first. Do not automatically escalate after a focused test passes.
- After a failure and corrective edit, rerun the failed or focused target first.
- Do not rerun an unchanged passing command for reassurance.
- Do not repeat a command when code, tests, environment, and inputs are unchanged and the failure mode is unchanged; identify the root cause or stop and report.
- Reserve `regression`, `matrix`, `all`, `ci`, and other broad gates for their intended risk or milestone.

Before creating a test, answer:

1. What unique failure would this catch?
2. Why can the nearest existing test not express it?
3. Why is this the lowest-cost appropriate test layer?

If answers are not concrete, do not add the test. When scope exposes obsolete or redundant tests, prefer minimal consolidation that keeps the strongest contract and reduces maintenance.

## Files, docs, and artifacts

- Honor `.agentignore` as a contract for files agents should not read, index, embed, or transmit unless explicit task instructions and repo policy permit it.
- Do not commit generated artifacts unless the task requires it. Ensure `.gitignore` covers new generated output.
- Model artifacts live in `models/`; runtime sidecars live in `runtimes/`; package/dependency metadata lives in `pyproject.toml`.
- Source code and tests describe the system as it exists. Development narration belongs in chat, commits, pull requests, or durable ADRs.
- When a change materially implements, removes, or changes behavior described by an accepted ADR, update the affected ADR `Status`, `Current Design`, `Remaining Work`, and `Evidence` sections in the same change. Use `Remaining Work` only for gaps required to complete that ADR's decision; move separate future architecture into a new ADR or backlog, and mark older ADRs superseded when a later decision replaces them.
- Default to no comment. Keep a comment only when it explains a non-obvious invariant, constraint, workaround, or public contract.
- Source artifacts contain no conversation/session residue, agent references, phase notes, temporary planning references, or completed-work justifications.
- Use positive scope boundaries: say what owns behavior, not what a module "is not."
- Cross-reference docs only where acting correctly requires reading the target.
- Helper artifacts are maintenance surfaces for approved designs, not design authority. Approved names: `docs/helpers/<area>-<purpose>.md`, `docs/helpers/<area>-<purpose>.ps1`, `docs/temp/<name>-YYYYMMDDHHMMSS.zip`.

## Git safety

Never run destructive Git operations without explicit approval, including `git restore`, `git reset`, `git clean`, `git rebase`, or history rewrites.
