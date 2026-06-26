# YYYYMMDD_slice-template.md
## Slice {Group} — {Short Title}

---

## Purpose

**What this section is for.** State the slice's single objective in one concise paragraph. Explain why this slice exists, what problem it solves, and what capability it introduces. This is the north star for the entire slice — every sub-slice and file should trace back to this purpose. Include the exact capability gap or architectural motivation that justifies this slice. Reference `ProjectVision.md` where applicable. Be specific about what "done" means at the architectural level.

---

## Baseline Consumed

**What this section is for.** List every pre-existing repository capability, file, or surface that this slice depends on and consumes unchanged. Each item should be verifiable from `SYSTEM_INVENTORY.md`, `CHANGE_LOG.md`, or direct file inspection.

Format as a bullet list. For each entry, state:
- What exists
- Where it lives (file path or domain)
- How this slice consumes it (e.g., "consumed unchanged", "extended", "imported")

This section prevents scope creep by making the baseline explicit. If a capability is claimed as baseline but does not actually exist, the slice must not begin until the gap is resolved.

---

## Out of Scope

**What this section is for.** Explicit non-goals for this slice. List capabilities, architectural changes, or file domains that this slice deliberately does not touch. This prevents reviewers or future agents from mistaking omission for oversight.

Format as a bullet list. Group by domain (e.g., "No Group X files", "No runtime changes", "No dependency changes"). Be specific about what is excluded — vague statements like "no other changes" are insufficient. Each out-of-scope item should correspond to something a reasonable reviewer might expect this slice to include.

---

## Pre-Implementation Gates

**What this section is for.** Prerequisites that must be resolved before the slice or specific sub-slices can begin. Each gate is a verification step, not an assumption. Gates prevent implementation from proceeding on unverified foundations and should easily be resolved by inspection only verification.

Format each gate as:
- **Gate {code} — {Title}.** Description of the prerequisite, why it matters, and how to verify it. If the gate requires a code change, a dependency addition, or an external tool check, state that explicitly. Resolution evidence is required before the dependent sub-slice begins.

Gates that are resolved before implementation can be marked `[Resolved]` with a short note. Gates that remain open must be resolved and recorded in `CHANGE_LOG.md` before the relevant sub-slice closes.

---

## New Directories and Files Created by This Slice

**What this section is for.** A tree-style or list overview of every new directory and file this slice introduces. This gives reviewers a structural map before diving into sub-slice details. Align with existing `repo_tree.md`.

Use a monospace-block file tree:
```
backend/app/new_domain/
    __init__.py
    core_module.py
config/new_config/
    config.yaml
backend/tests/unit/new_domain/
    test_core_module.py
```

Include only files that are created (not modified). Modified files are listed per sub-slice in the Scope section.

---

## Execution Order

**What this section is for.** The required sequence of sub-slices. Each sub-slice must compile, unit-pass, and (where applicable) script-smoke-pass before the next begins. Dependencies between sub-slices are explicit.

Format as:
```
N.1 → N.2 → N.3 → ...
```
Or if pre-implementation gates exist:
```
Gate-1 resolved → N.1 → Gate-2 resolved → N.2 → N.3
```

State the rule: "Each sub-slice must reach its unit PASS before the next begins. Slice {prior group} regression must remain green after every sub-slice."

---

## Sub-Slice N.1 — {Sub-Slice Title}

**What this section is for.** The smallest meaningful unit of implementation within the slice. Each sub-slice is independently reviewable, testable, and closeable.

Every sub-slice should contain the following subsections:

### Goal

A one-paragraph objective statement. What capability does this sub-slice add? What is the observable behavior change?

### Scope

List of files to create (with a brief description of what each contains) and files to modify (with a description of the change). For each file, state:
- File path relative to repo root
- What it does (one line)
- Key design decisions or constraints embedded in it

### Files Not to Modify

Explicit list of files or directories that any implementation agent must not change during this sub-slice. This prevents accidental scope expansion.

### Validation

A numbered sequence of CLI commands to run for validation. Each command should be a separate step. Include both compile checks, unit tests, and any live/smoke tests. Select from the venv-prefixed command patterns as appropriate:
```
backend/.venv/Scripts/python -m compileall backend/app/new_module
backend/.venv/Scripts/python -m pytest backend/tests/unit/new_module -q
backend/.venv/Scripts/python scripts/validate_backend.py unit
backend/.venv/Scripts/python scripts/validate_backend.py regression
backend/.venv/Scripts/python scripts/validate_backend.py runtime --families <family> --devices cpu
```

Add a NOTE if validation depends on a provisioned venv or external service, so the implementer knows to skip change-logging if the prerequisite is not yet met.

### Acceptance

A checklist of expected evidence for each validation step. Format as a block:
```
PASS compile: ...
PASS unit: ...
PASS live cpu: ...
PASS regression: ...
```

`FAIL` is never an allowed closeout state. If a test cannot pass, it must `SKIP-<reason>`. The reason must be documented and acceptable per slice-level criteria.

---

## File Placement Summary

**What this section is for.** A table of every file touched (created or modified) by this slice, organized by sub-slice. This serves as the implementation checklist and governance record.

Format as a markdown table with columns: `File`, `Action` (New / Modify / Extend), `Sub-slice`. Optionally add a "Must not create" subsection listing file paths that must remain absent at closeout.

| File | Action | Sub-slice |
|------|--------|-----------|
| `backend/app/new_module/file.py` | New | N.1 |
| `backend/app/existing.py` | Extend | N.2 |
| `CHANGE_LOG.md` | Append | Per sub-slice |
| `SYSTEM_INVENTORY.md` | Append | N.n closeout |

---

## Slice-Level Closeout Criteria

**What this section is for.** A numbered checklist of boolean conditions that must all be true for the slice to be complete. This is the authoritative completion definition.

Each criterion should be:
- Observable and testable (not subjective)
- Tied to specific validation commands or file states
- Host-class-aware where applicable (e.g., "on both Windows x64 and Windows ARM64")
- Independent of other criteria (no compound conditions)

---

## Documentation / Update Policy

**What this section is for.** Rules for when and how to update governance files (`CHANGE_LOG.md`, `SYSTEM_INVENTORY.md`, etc.) during and after this slice. This protects against premature claims or forgotten updates.

Standard rules to include or adapt:
- `CHANGE_LOG.md`: one entry per sub-slice after validation is confirmed.
- `SYSTEM_INVENTORY.md`: one entry at slice closeout (or per sub-slice if the slice is large). State: `Verified`.
- Inventory notes should document any SKIP states, known limitations, skipped capabilities, and explicit exclusions of out-of-scope groups.
- Use append-only corrections if prior records need qualification; never rewrite history.

---

## Finish Line

**What this section is for.** A concise summary paragraph that restates the slice's purpose in past-tense completion language. This is what the `CHANGE_LOG.md` entry and `SYSTEM_INVENTORY.md` note will reference.

It should read as if the slice is already complete. List the capabilities now present that did not exist before, and explicitly restate what was not introduced. Example:

> Group X is complete when {capability A} is proven on both host classes, {capability B} is testable and fail-closed, and no {out-of-scope capabilities} exist in the repository.

---

## Risks / Sequencing Notes

**What this section is for.** (Brief/Concise) A table or bullet list of known risks, hazards, or sequencing dependencies that could block or delay the slice. This is not speculative — each risk should have a specific mitigation path.

Format each risk as:
| Risk | Severity | Mitigation |
|------|----------|------------|
| {Specific risk} | Low / Medium / High | {Specific action or fallback} |

Include dependencies that are outside the slice's control, such as external package availability, hardware availability for validation, or upstream slice delays.