# AGENTS.md: Agent Operating Contract for JARVISv7

Authoritative contract for all AI and human agents. Loaded every session. Keep current; stale rules mislead.

## Instruction Weighting

Agents MUST interpret sections as:
- CRITICAL → always enforce
- REQUIRED → enforce when relevant
- OPTIONAL → consult only if task touches that domain

OPTIONAL sections SHOULD be ignored if unrelated to reduce cognitive load.

---

## 1. Highest Priority: Python Environment Isolation (CRITICAL)

- Use `backend/.venv` for all Python.
- Never use global Python packages.
- Never install dependencies globally.
- Run from repo root (`pyproject.toml` location).

Dependencies:

- `pyproject.toml` = sole source of truth.
- `backend/requirements.txt` = generated lockfile via `scripts/provision.py lock`. Never edit manually.
- Hardware packages defined via `[project.optional-dependencies]`.
- Declare new deps in proposal; install only after provisioning.
- Default operator `>=`; use `==` only with documented justification.
- ML/runtime-specific packages NEVER in base dependencies.

Provisioning authority:

- `scripts/provision.py` is the ONLY installer.
- Commands:
  - install: `backend/.venv/Scripts/python scripts/provision.py install`
  - verify: `... verify`
  - lock: `... lock`
  - explain: `... explain`
- Never run `pip install` directly.

Required command pattern (PowerShell, repo root):

- `backend/.venv/Scripts/python <command>`

First-time setup:

1. `python -m venv backend/.venv`
2. `backend/.venv/Scripts/python -m pip install --upgrade pip`
3. `backend/.venv/Scripts/python scripts/provision.py install`

Prefer `scripts/bootstrap.py` for full setup.

If venv is broken → STOP and report minimal repair steps.

---

## 2. Core Operating Constraints (CRITICAL)

- Do not guess; if unverifiable, report checks and stop.
- Do not claim completion without reproducible evidence.
- Do not expand scope.
- Do not create new artifacts unless requested.
- No parallel/shadow systems.
- Prefer existing patterns and minimal diffs.
- Output concise, evidence-focused.

Programming principles:

- Reuse existing patterns first.
- Test → Configure → Install.
- KISS, DRY, YAGNI.
- Idempotent and deterministic operations.
- Separate concerns (single responsibility per change).

---

## 3. Hardware Architecture Awareness (REQUIRED)

- No runtime host detection outside:
  - `backend/app/hardware/profiler.py`
  - `backend/app/hardware/provisioning.py`
- No DLL/bootstrap logic outside `preflight.py`.
- Voice runtimes MUST accept `device` parameter; extend via branching, not new files.
- Always state affected/unaffected host classes in proposals and validation.
- Always state host class for evidence.

---

## 4. Deterministic Execution Rules (CRITICAL)

- Execution must be deterministic and approval-gated.
- Use explicit, reproducible commands.
- Prefer non-interactive flags.
- Validate small → expand only if needed.
- If failure mode unchanged → STOP.
- No silent retries.
- One command per step (no chaining `&&`, `;`, etc.).
- Compound syntax allowed only when inherently required.

---

## 5. Approval-Gated Change Control (CRITICAL)

Require proposal BEFORE modifying:

- Multiple files
- Core backend systems
- Tests / validation harnesses
- Scripts
- Desktop (`desktop/`)
- Docker surfaces
- Dependencies (`pyproject.toml`)
- Environment repair
- Metadata / tooling config

Proposal MUST include:

- Files to modify
- Host classes affected
- Commands to run
- Expected evidence

STOP until approved.

---

## 6. Authoritative Truth Sources (REQUIRED)

Precedence:

1. AGENTS.md  
2. ProjectVision.md  
3. repo_tree.md  
4. SYSTEM_INVENTORY.md  
5. CHANGE_LOG.md  
6. slices.md  

On conflict → report + propose smallest correction.

---

## 7. Agent Ignore Policy (CRITICAL)

Agents MUST honor `.agentignore`.

- Uses `.gitignore` syntax
- Recursively discovered
- Rules combined
- Matches excluded from:
  - reading
  - indexing
  - embedding
  - transmission
- Treated as non-existent
- Cannot be overridden unless repo explicitly allows

Purpose: protect sensitive data, reduce noise.

---

## 8. Scripts (REQUIRED)

All scripts:

- Reside in `scripts/`
- Orchestrate `backend/app/**`
- Accept: `--verbose`, `--dry-run`, `--trace-to`
- Emit host-fingerprint first

Key scripts:

- `bootstrap.py` — full host setup pipeline
- `provision.py` — sole dependency installer
- `ensure_models.py` — model management
- `run_backend.py` — API only
- `run_jarvis.py` — proving host (NOT durable surface)
- `validate_backend.py` — sole validation system

---

## 9. Validation Requirements (REQUIRED)

- Validate observable behavior only.
- Include:
  - exact commands
  - PASS / FAIL / SKIPPED
  - minimal output proof
- Always state host class.
- Evidence must prove repeatability.

Validator (`scripts/validate_backend.py`):

- profile, unit, integration, runtime, regression, matrix, all, ci
- Exit codes:  
  0 pass / 1 fail / 2 skipped / 3 env issue

Use validator for governance evidence. Raw pytest = dev-only.

Test architecture:

- Marker-based (not directory split):
  x64, arm64, cuda, directml, qnn, live, slow, requires_*, stt, tts, llm, wake, turn, desktop, agents
- `conftest.py` exposes `skip_unless_*`
- Structure:
  - unit/
  - integration/
  - runtime/

Coverage:

- Backend `*.py` should have pytest coverage
- Minimum: import validation
- Preferred: behavior validation

Frontend:

- Use existing tooling only
- No alternate runtime paths

Warnings:

- Backlog unless affecting correctness/safety

---

## 10. Task Execution Workflow (CRITICAL)

1. Discover minimal file scope
2. Confirm constraints + host impact
3. Propose (if required)
4. Implement approved changes only
5. Validate
6. Report with proof + host class
7. STOP

Testing:

- Maintain pytest coverage
- Use correct markers
- Minimum: import validation
- Preferred: behavior validation

No follow-up work unless requested.

---

## 11. File and Artifact Boundaries (REQUIRED)

- No runtime artifacts in repo root
- Use existing dirs (`data/`, `cache/`, `reports/`, `models/`)
- No new storage without approval
- Ensure `.gitignore` covers generated artifacts
- `backend/requirements.txt` is generated only
- `config/hardware/notes.md` = human prerequisites only
- Model artifacts ONLY in `models/`

---

## 12. CHANGE_LOG.md Requirements (OPTIONAL)

- Append-only; never edit history
- Newest entries first under `## Entries`
- Log only after validation
- Factual, past tense
- Corrections = new entry

Required fields:

- Timestamp
- Summary
- Scope
- Host class
- Evidence

---

## 13. SYSTEM_INVENTORY.md Requirements (OPTIONAL)

- Record ONLY observable artifacts
- No inferred intent
- One entry = one capability
- New entries at top
- Corrections under `## Appendix`

Fields:

- Capability
- State
- Location
- Validation (with host class)
- Notes (optional)

No promotion without validation.

---

## 14. Git Safety Rules (OPTIONAL)

Require approval before:

- `git restore`
- `git reset`
- `git clean`
- `git rebase`
- history rewrites

Rollback → propose safest approach.

---

## 15. Reporting Format (REQUIRED)

All reports MUST include:

- Summary
- Host class
- Files inspected/changed
- Commands + outcomes
- Minimal evidence excerpt

No claim without command evidence.