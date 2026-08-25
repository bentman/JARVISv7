# YYYYMMDD_slice-template.md
## Slice {Group} — {Short Title}

> Status: planned.
> This document is an implementation contract.
> It is not completion evidence.

---

## Purpose

State the slice's single objective in one or two concise paragraphs. Describe the capability gap, why this slice exists, and what observable behavior will be true when the slice is complete.

Every sub-slice, file touch, validation command, and closeout criterion must trace back to this purpose.

---

## Implementation Contract

State the rules that constrain repository changes for this slice.

Include only rules that constrain implementation. Avoid restating the whole repository contract unless the slice needs a sharper boundary.

Required baseline rules:

- Preserve existing validated behavior unless this slice explicitly changes it.
- Do not create parallel mechanisms when the existing architecture can be extended.
- Keep scope limited to the files and behavior named in this slice.
- Add or update focused tests with each behavior change.
- Record validation evidence before governance updates.
- Do not update `SYSTEM_INVENTORY.md` until the capability is verified on both Windows AMD64 and Windows ARM64, unless the user explicitly approves a narrower inventory state.
- Keep source, test, and documentation text free of authoring-session, task-history, implementation-phase, diff, and completed-work narration.
- Default to no source comment; retain comments only for non-obvious invariants, constraints, workarounds, or public contracts.
- State positive ownership boundaries: identify what owns behavior and evidence rather than describing rejected mechanisms.
- Link between repository documents only in approved hub or ADR consequence sections, and only when correct operation requires the target.

Add slice-specific rules below:

- {Rule 1}
- {Rule 2}
- {Rule 3}

---

## Baseline Consumed

List the existing repository capabilities, files, APIs, configs, scripts, or UI surfaces this slice consumes. Each item must be verifiable by direct inspection or existing governance evidence.

Use this form:

- `{path-or-surface}` already provides {existing behavior}. This slice {extends/uses/observes} it by {specific relationship}. Boundary: {what must not be inferred or changed}.
- `{path-or-surface}` already provides {existing behavior}. This slice {extends/uses/observes} it by {specific relationship}. Boundary: {what must not be inferred or changed}.

If a claimed baseline is missing, stop and resolve that gap before implementation.

---

## Out of Scope

List non-goals explicitly. These should be concrete enough to prevent scope expansion.

- No {nearby capability not included}.
- No {architecture/runtime/setup/UI/domain outside this slice}.
- No {artifact/dependency/external integration unless explicitly required}.
- No {governance claim beyond available evidence}.

---

## Target Observable Behavior

Describe the intended behavior without over-specifying implementation. Use the smallest form that makes success clear.

Examples of acceptable observable targets:

- Command behavior: `{command}` produces `{expected output/state}`.
- API behavior: `{endpoint/schema}` includes `{field/state}`.
- Runtime behavior: `{condition}` selects/runs/reports `{expected result}`.
- UI behavior: `{surface}` shows/allows/prevents `{expected behavior}`.
- Governance behavior: `{file}` records `{evidence}` only after `{validation}`.

If the slice has user/operator-facing behavior, include a short sketch:

```text
Control/status: {label or field}
Active value: {resolved value}
Reason/evidence: {why this value is active}
Advanced/details: {optional raw detail, if any}
```

If the slice is internal only, state: `No direct user-facing surface; behavior is observable through {tests/logs/API/status/etc.}`

---

## Vocabulary / Contract Terms

Define only terms that could otherwise be ambiguous across code, tests, docs, and reports.

- **{term}**: {definition}.
- **{term}**: {definition}.
- **{selected/active/current value}**: {definition, if applicable}.
- **{degraded/skipped/fallback state}**: {definition, if applicable}.

Delete this section if the slice uses only existing project vocabulary.

---

## Design Shape / Contract Sketch

Use this section only when a structural sketch prevents ambiguity. Keep it generic and close to the existing architecture.

```text
{input or source}
  -> {selection/resolution/processing step}
  -> {existing mechanism or output}
  -> {observable evidence}
```

Optional structured sketch:

```yaml
{top_level_key}:
  {policy_or_mode}:
    {selector}: {target}
```

Rules:

- Show form, not final implementation detail.
- Mark placeholders explicitly.
- Do not imply planned capability is already implemented.
- If the required behavior or evidence boundary changes materially, update this slice doc before continuing.

---

## Execution Order

Declare the required sequence. Use the smallest set of sub-slices that preserves dependency order.

```text
{Group}.0 baseline capture -> {Group}.1 foundation -> {Group}.2 core behavior -> {Group}.3 integration -> {Group}.4 user/setup/docs surface -> {Group}.5 closeout
```

Rules:

- Each sub-slice must pass its focused validation before the next begins.
- Changes to broad setup, runtime selection, persistence, or cross-host behavior require regression validation before closeout.
- Do not perform governance closeout until implementation validation is complete.

---

## Sub-Slice {Group}.0 — Baseline Capture

### Goal

Capture or consume verified current behavior before repository changes so later failures can be separated from intentional contract changes.

### Scope

Inspect or consume verified evidence for:

- `{path-or-surface}` — {why inspected}.
- `{path-or-surface}` — {why inspected}.
- `{existing-test-or-validation-area}` — {why inspected}.

### Evidence Reuse Rules

- A Sub-Slice 0 baseline may consume results already present in the active execution context when each result includes the exact command, outcome, host class, and minimal output excerpt or report path.
- Confirm that relevant tracked code, configuration, test targets, dependencies, and host facts have not changed since the consumed result.
- Rerun evidence when its command or target changed, relevant repository state changed, the host environment changed materially, required fields are missing, or the result is no longer reproducible with reasonable confidence.
- Do not copy generated reports into tracked files solely to preserve contextual evidence.

### Ownership Boundaries

- Repository files remain unchanged during baseline capture unless an explicitly approved baseline test is required.
- Existing validation commands and reports own executable baseline evidence.
- This contract or the closeout record owns the concise command, outcome, host class, and evidence summary.

### Validation

```text
{command 1}
{command 2}
```

### Acceptance

```text
PASS or documented pre-existing failure for baseline validation.
No implementation files changed.
Baseline behavior recorded in this contract or closeout evidence.
```

---

## Sub-Slice {Group}.1 — {Foundation Title}

### Goal

Add the minimum foundation needed for later sub-slices. This should avoid broad behavior changes unless the foundation itself is the behavior.

### Scope

Create/modify:

- `{path}` — {intended change}.
- `{path}` — {intended change}.

### Ownership Boundaries

- `{path-or-area}` owns {behavior or evidence retained unchanged}.
- `{path-or-area}` owns {behavior or evidence retained unchanged}.

### Validation

```text
{focused command}
```

### Acceptance

```text
PASS focused validation.
New contract is represented in tests or validation output.
No out-of-scope behavior changed.
```

---

## Sub-Slice {Group}.2 — {Core Behavior Title}

### Goal

Implement the central behavior of the slice in the smallest testable unit.

### Scope

Create/modify:

- `{path}` — {intended change}.
- `{path}` — {intended change}.

State key precedence, fallback, or fail-closed rules if applicable:

1. {Rule or precedence step}.
2. {Rule or precedence step}.
3. {Failure/skip/degraded behavior}.

### Ownership Boundaries

- `{path-or-area}` owns {behavior or evidence retained unchanged}.

### Validation

```text
{focused command}
{related command}
```

### Acceptance

```text
PASS focused validation.
Expected success path works.
Expected failure/degraded path is explicit and tested.
```

---

## Sub-Slice {Group}.3 — {Integration Title}

### Goal

Wire the core behavior into the existing repository path that owns the user-visible or runtime-visible result.

### Scope

Create/modify:

- `{path}` — {intended change}.
- `{path}` — {intended change}.

### Ownership Boundaries

- `{path-or-area}` owns {behavior or evidence retained unchanged}.

### Validation

```text
{focused integration command}
{profile/smoke command, if applicable}
```

### Acceptance

```text
PASS integration validation.
Selected/active behavior is observable through the intended surface.
Existing fallback/degraded states remain truthful.
```

---

## Sub-Slice {Group}.4 — {Surface / Setup / Documentation Title}

### Goal

Expose the behavior through the appropriate user, operator, setup, API, or documentation surface. Delete this sub-slice if there is no such surface.

### Scope

Create/modify:

- `{path-or-surface}` — {intended change}.
- `{path-or-surface}` — {intended change}.

### Ownership Boundaries

- `{path-or-area}` owns {behavior or evidence retained unchanged}.

### Validation

```text
{focused surface/setup command}
{static/UI/API/doc validation command, if applicable}
```

### Acceptance

```text
PASS focused validation.
Surface shows the new behavior without hiding raw evidence or degraded state.
Normal user path remains simple.
Advanced or diagnostic paths remain available where required.
```

---

## Sub-Slice {Group}.5 — Closeout Evidence and Governance

### Goal

Record completion only after validation evidence exists. Do not use this sub-slice to finish implementation work.

### Scope

Modify after validation:

- `CHANGE_LOG.md` — append validation-backed entry.
- `SYSTEM_INVENTORY.md` — append/update only after both Windows AMD64 and Windows ARM64 verification exists, unless explicitly approved otherwise.
- `{user-facing-doc}` — update only if user-facing behavior changed.
- `{slice-doc-location}` — move/update only if current repo practice requires it.

### Validation

```text
{profile command}
{unit command}
{regression command}
{surface/static/runtime command, if applicable}
```

### Acceptance

```text
PASS required validation on implementing host.
PASS or SKIP-with-reason for optional/live/runtime validation.
CHANGE_LOG.md records exact command, outcome, host class, and minimal evidence.
SYSTEM_INVENTORY.md is updated only with required host-class evidence or explicit user approval.
No planned/future capability is recorded as verified.
```

---

## File Placement Summary

| File or Area | Action | Sub-slice | Notes |
|---|---|---|---|
| `{path-or-area}` | New / Extend / Inspect / Append | `{Group}.n` | {short note} |
| `{path-or-area}` | New / Extend / Inspect / Append | `{Group}.n` | {short note} |

Must not create unless explicitly approved:

- `{forbidden-path-or-pattern}`
- `{forbidden-path-or-pattern}`

---

## Validation Matrix

Use this table to declare required evidence. Delete rows that do not apply.

| Validation target | Host class | Command or method | Required for closeout? | Expected result |
|---|---|---|---|---|
| Baseline/focused test | `{host}` | `{command}` | Yes / No | PASS or documented pre-existing failure |
| Integration/profile check | `{host}` | `{command}` | Yes / No | PASS |
| Regression | `{host}` | `{command}` | Yes / No | PASS |
| Runtime/live check | `{host}` | `{command or method}` | Yes / No | PASS or SKIP-with-reason |
| User/operator validation | `{host}` | `{method}` | Yes / No | Accepted / rejected |
| Inventory eligibility | Windows AMD64 + Windows ARM64 | `{commands/evidence}` | Yes for inventory | PASS on both, unless explicitly approved otherwise |

---

## Slice-Level Closeout Criteria

All criteria must be observable and testable.

1. {Primary capability is implemented through the intended architecture}.
2. {Focused tests cover success behavior}.
3. {Focused tests cover failure/degraded behavior, if applicable}.
4. {Integration surface reports the active state truthfully}.
5. {No out-of-scope files or behavior changed}.
6. {Required validation commands pass or skip with explicit acceptable reason}.
7. `CHANGE_LOG.md` is updated only after validation evidence exists.
8. `SYSTEM_INVENTORY.md` is updated only after both Windows AMD64 and Windows ARM64 evidence exists, unless explicitly approved otherwise.

---

## Documentation and Governance Policy

- `CHANGE_LOG.md`: append only after validation. Include exact command, outcome, host class, and minimal evidence excerpt or report path.
- `SYSTEM_INVENTORY.md`: update only after the capability is verified on both Windows AMD64 and Windows ARM64, unless the user explicitly approves a narrower inventory state.
- User-facing docs: update only when user-facing setup, operation, or behavior changes.
- Source and test text: describe active behavior, ownership, invariants, and public contracts without authoring-session, task-history, implementation-phase, diff, or completed-work narration.
- Comments: omit by default; retain only when they explain a non-obvious invariant, constraint, workaround, or public contract.
- Scope boundaries: state which mechanism owns behavior and evidence.
- Cross-references: link between repository documents only in approved hub sections or an ADR's own Consequences section, and only when required for correct operation.
- Slice docs: update the contract before continuing when required behavior or evidence boundaries change materially.
- Use append-only corrections for governance files; do not rewrite history.

---

## Risks and Sequencing Notes

| Risk | Severity | Mitigation |
|---|---|---|
| {Specific risk} | Low / Medium / High | {Specific mitigation} |
| {Specific risk} | Low / Medium / High | {Specific mitigation} |

Include only risks that can affect implementation order, validation, user behavior, or governance accuracy.

---

## Finish Line

Slice {Group} is complete when {capability} is implemented through the intended repository path, validated with the required evidence, and documented without overclaiming host-specific, future, skipped, or degraded capability.
