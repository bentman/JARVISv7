# YYYYMMDD_slice-template.md
## Slice {Group} — {Short Title}

Status: planned. This document is an implementation contract for the next coding agent. It is not completion evidence.

---

## Purpose

State the slice's single objective in one or two concise paragraphs. Describe the capability gap, the architectural reason this slice exists, and the observable behavior that will be true when the slice is complete.

Every sub-slice, file touch, validation command, and closeout criterion must trace back to this section.

---

## Agent Contract

Implementation agents must follow these rules:

- Preserve the existing architecture unless this slice explicitly changes it.
- Do not create duplicate managers, launchers, setup flows, runtime paths, or desktop-only state for backend-owned behavior.
- Keep generated/runtime data in existing approved roots only: `data/`, `cache/`, `reports/`, `models/`, or `runtimes/`.
- Make new runtime/config decisions observable through status, readiness, logs, tests, or validation output.
- Keep raw overrides as escape hatches, not the primary user experience, when a curated operator path is possible.
- Add or update focused tests with each behavior change.
- Append `CHANGE_LOG.md` only after validation evidence exists.
- Do not update `SYSTEM_INVENTORY.md` until the capability is verified on both Windows AMD64 and Windows ARM64, unless the user explicitly approves a narrower inventory state.

Add slice-specific rules here.

---

## Baseline Consumed

List the existing repository surfaces this slice consumes. Each item should be verifiable by direct file inspection, `SYSTEM_INVENTORY.md`, or `CHANGE_LOG.md`.

- `path/to/file.py` already does {existing behavior}. This slice extends it by {specific extension}; it does not replace {boundary}.
- `config/example.yaml` already declares {existing config}. This slice adds {specific metadata} while preserving {existing shape}.
- `scripts/example.py` already runs {existing setup/validation}. This slice keeps that entry point and changes only {specific behavior}.

If a claimed baseline is not present, stop and resolve that gap before implementation.

---

## Out of Scope

List explicit non-goals.

- No {related capability that may be tempting but is not part of this slice}.
- No {runtime/dependency/setup redesign outside the slice}.
- No {new artifacts, external services, or live integrations unless explicitly required}.
- No {governance claim beyond available validation evidence}.

---

## Target User Experience / Observable Behavior

Describe the intended user/operator behavior in concrete terms. Include commands, UI shape, API response shape, or runtime behavior as appropriate.

```powershell
backend\.venv\Scripts\python scripts\bootstrap.py
```

Default behavior should be:

1. Detect current host/profile.
2. Resolve the relevant policy/config.
3. Apply the selected backend mechanism.
4. Report the active decision and any degraded candidates in readiness/status.
5. Keep advanced overrides available but secondary.

Operator-facing sketch when applicable:

```text
Primary setting: <curated control>
Active value: <resolved value>
Selected because: <short reason>
Advanced: <raw overrides or diagnostics>
```

Omit this section only if the slice is strictly internal.

---

## Slice Vocabulary / Contract Terms

Define terms that must be used consistently in code, config, tests, UI, and closeout reporting.

- **term one**: exact meaning in this slice.
- **policy**: the user/operator or default strategy used to derive a selected value.
- **selected value**: the concrete value passed into the existing runtime/config path.
- **degraded candidate**: an unavailable or skipped option that must be reported truthfully, not treated as a pass.

Omit or shorten this section for small slices.

---

## Proposed Shape / Design Sketch

Use this section for the desired config/API/module shape when it helps avoid ambiguity. It is a sketch, not completion evidence. Keep it close to the current architecture.

```yaml
example_policy:
  default: auto
  policies:
    auto:
      windows_amd64_cpu: baseline
      windows_arm64_cpu: baseline
    diagnostic:
      "*": diagnostic
```

Rules:

- Show only the minimum structure needed to guide implementation.
- Do not imply future capability is implemented.
- Mark placeholders or future targets explicitly.
- Keep final implementation close to this shape or update the slice doc before continuing.

---

## Execution Order

```text
{Group}.0 baseline contract capture -> {Group}.1 foundation/metadata -> {Group}.2 backend/core mechanism -> {Group}.3 startup/readiness/API integration -> {Group}.4 setup integration -> {Group}.5 operator/UI integration -> {Group}.6 closeout validation/docs
```

Rule: each sub-slice must pass its focused validation before the next begins. Full regression is required at closeout and after changes to setup scripts, runtime selection, persistence, or cross-host behavior.

---

## Sub-Slice {Group}.0 — Baseline Contract Capture

### Goal

Capture current behavior before implementation so later failures can be separated from intentional contract changes.

### Scope

Inspect only:

- `path/to/current/config.yaml`
- `backend/app/current/module.py`
- `scripts/current_setup.py`
- relevant existing tests under `backend/tests/unit/...`

### Files Not to Modify

All files. This is read-only except for optional notes in the agent's final report.

### Validation

```powershell
backend\.venv\Scripts\python -m pytest backend\tests\unit\<focused-area> -q
backend\.venv\Scripts\python scripts\validate_backend.py profile
```

### Acceptance

```text
PASS focused baseline tests or record pre-existing failure before edits.
PASS/SKIP profile or setup command with clear reason.
No source files modified.
```

---

## Sub-Slice {Group}.1 — {Foundation / Metadata / Contract Title}

### Goal

Add the smallest foundation needed for later behavior without changing runtime behavior yet.

### Scope

Modify:

- `config/...` — add metadata or policy shape.
- `backend/app/...` — add schema/catalog tolerance if required.
- `backend/tests/unit/...` — assert the new metadata contract.

### Files Not to Modify

- Runtime launcher files.
- Desktop files.
- Governance files until validation passes.

### Validation

```powershell
backend\.venv\Scripts\python -m pytest backend\tests\unit\<focused-area> -q
```

### Acceptance

```text
PASS focused unit tests.
New metadata/config validates.
Runtime behavior remains unchanged.
```

---

## Sub-Slice {Group}.2 — {Backend/Core Mechanism Title}

### Goal

Implement the pure backend/core mechanism. This should be testable without desktop, live services, or broad setup changes.

### Scope

Create or modify:

- `backend/app/<domain>/<new_module>.py` — pure resolver/selector/service logic.
- `backend/tests/unit/<domain>/test_<new_module>.py` — success, fallback, invalid config, and fail-closed tests.
- `backend/app/core/settings.py` — new settings only if needed.
- `backend/app/api/routes/config.py` — allowlisted operator config only if needed.

State precedence rules explicitly when relevant.

### Files Not to Modify

- Desktop files.
- Runtime launcher/sidecar files unless this sub-slice explicitly owns them.
- Setup scripts unless this sub-slice explicitly owns setup behavior.

### Validation

```powershell
backend\.venv\Scripts\python -m pytest backend\tests\unit\<domain>\test_<new_module>.py -q
backend\.venv\Scripts\python -m pytest backend\tests\unit\api\test_routes.py -q
```

### Acceptance

```text
PASS focused mechanism tests.
Invalid input fails closed with a clear reason.
Existing default path still works.
```

---

## Sub-Slice {Group}.3 — {Startup / Runtime / Readiness Integration Title}

### Goal

Wire the new mechanism into the existing runtime/API path and make the selected decision observable.

### Scope

Modify:

- `backend/app/services/...` — call the new resolver/mechanism before the existing runtime path.
- `backend/app/routing/...` — add trace fields only if needed.
- `backend/app/api/schemas/readiness.py` — expose selected decision metadata.
- `backend/app/api/routes/readiness.py` — include selected decision metadata and degraded reasons.
- relevant focused tests.

### Files Not to Modify

- Do not fork the existing runtime path.
- Do not introduce a new setup entry point.
- Do not modify desktop until the API/readiness contract is tested.

### Validation

```powershell
backend\.venv\Scripts\python -m pytest backend\tests\unit\services\<focused_test>.py backend\tests\unit\api\test_routes.py -q
backend\.venv\Scripts\python scripts\validate_backend.py profile
```

### Acceptance

```text
PASS startup/service/API focused tests.
PASS profile validator.
Readiness/status reports selected value, policy/reason, active runtime/profile, and degraded candidates where applicable.
```

---

## Sub-Slice {Group}.4 — {Setup / Provision / Ensure Integration Title}

### Goal

Integrate the mechanism into first-run setup and validation without making setup broader or harder for the user.

### Scope

Modify:

- `scripts/ensure_models.py` or the relevant setup script — default behavior follows selected policy/current host.
- `scripts/bootstrap.py` only if the existing bootstrap command must pass a new flag; prefer preserving the command.
- `scripts/provision.py` only if dependency planning or explanation must change.
- script unit tests.

CLI rules to define when relevant:

- Default command uses selected/current-host behavior.
- Explicit `--model`, `--policy`, or equivalent remains supported.
- Explicit `--all-*` remains available for full-catalog validation.
- Non-target families or domains remain unchanged.

### Files Not to Modify

- Desktop files.
- Runtime command construction unless setup validation exposes a shared contract gap.
- Artifact directories.

### Validation

```powershell
backend\.venv\Scripts\python -m pytest backend\tests\unit\scripts\<focused_script_test>.py -q
backend\.venv\Scripts\python scripts\<setup_script>.py --verify-only
backend\.venv\Scripts\python scripts\bootstrap.py --dry-run
```

### Acceptance

```text
PASS script unit tests.
PASS selected/default setup verification.
PASS explicit all-catalog/full verification if applicable.
PASS bootstrap dry-run.
Default setup does not acquire or validate unrelated future artifacts.
```

---

## Sub-Slice {Group}.5 — {Operator / Desktop / UX Integration Title}

### Goal

Expose the capability through a simple operator-facing control or status surface, while preserving advanced/raw controls where needed.

### Scope

Modify:

- `backend/app/api/routes/config.py` and schemas if the Operator needs curated field metadata.
- `desktop/src/components/...` — grouped or curated operator control.
- `desktop/src/main.js` only if wiring needs refresh/state changes.
- `desktop/src/style.css` only for compact grouping.
- desktop/static contract tests.

UX constraints:

- Prefer select/toggle/status controls over raw text for curated settings.
- Group raw overrides under Advanced.
- Preserve restart-required behavior.
- Do not hide readiness/status truth when an override is active.
- Use DOM-safe rendering for dynamic content.

### Files Not to Modify

- Core backend mechanism unless a desktop test exposes a backend contract gap.
- Setup scripts after the setup sub-slice unless required.

### Validation

```powershell
backend\.venv\Scripts\python -m pytest backend\tests\unit\api\test_routes.py backend\tests\unit\desktop\test_desktop_static_contract.py -q
npm --prefix desktop test
```

### Acceptance

```text
PASS API route tests.
PASS desktop static contract tests.
PASS npm desktop tests.
Operator UX is curated-first and advanced overrides remain available.
```

---

## Sub-Slice {Group}.6 — Closeout Evidence and Documentation

### Goal

Record governance only after validation evidence exists. Do not use this sub-slice to finish implementation work.

### Scope

Modify after validation:

- `CHANGE_LOG.md` — append one concise entry per validated sub-slice or one consolidated slice entry if implementation was single-pass.
- `SYSTEM_INVENTORY.md` — append/update only after the capability is verified on both Windows AMD64 and Windows ARM64, unless the user explicitly approves a narrower inventory state.
- `docs/QuickStart.md` only if setup commands or user-facing behavior changed.
- `README.md` only if project-level capability description changed.
- Move completed slice doc to `docs/slices-done/` only after completion, if that is the current repo practice.

### Validation

Minimum closeout commands:

```powershell
backend\.venv\Scripts\python scripts\validate_backend.py profile
backend\.venv\Scripts\python scripts\validate_backend.py unit
backend\.venv\Scripts\python scripts\validate_backend.py regression
npm --prefix desktop test
```

When host-specific behavior is involved, collect both host classes before inventory.

### Acceptance

```text
PASS profile validator on implementing host.
PASS unit validator on implementing host.
PASS regression validator on implementing host.
PASS desktop checks if desktop changed.
PASS/SKIP-with-reason runtime validation where applicable.
CHANGE_LOG.md records exact commands and host class.
SYSTEM_INVENTORY.md is updated only when both Windows AMD64 and Windows ARM64 evidence exists, or when the user explicitly approved narrower inventory logging.
No future capability is claimed from placeholders or planned config.
```

---

## File Placement Summary

| File | Action | Sub-slice |
|------|--------|-----------|
| `config/...` | Extend | {Group}.1 |
| `backend/app/<domain>/<module>.py` | New/Extend | {Group}.2 |
| `backend/tests/unit/<domain>/test_<module>.py` | New/Extend | {Group}.2 |
| `backend/app/api/schemas/readiness.py` | Extend if needed | {Group}.3 |
| `backend/app/api/routes/readiness.py` | Extend if needed | {Group}.3 |
| `scripts/<setup>.py` | Extend if needed | {Group}.4 |
| `desktop/src/components/<component>.js` | Extend if needed | {Group}.5 |
| `backend/tests/unit/desktop/test_desktop_static_contract.py` | Extend if desktop changed | {Group}.5 |
| `CHANGE_LOG.md` | Append after evidence | {Group}.6 |
| `SYSTEM_INVENTORY.md` | Append/update only after AMD64 + ARM64 verification | {Group}.6 |
| `docs/QuickStart.md` | Extend if user-facing setup changed | {Group}.6 |

Must not create unless explicitly approved:

- new parallel setup scripts
- new runtime roots outside approved `runtimes/` structure
- generated artifacts outside approved generated/runtime roots
- desktop-only state files for backend-owned behavior

---

## Host-Class / Profile Matrix

Use this table when behavior varies by host, runtime, accelerator, or profile. Delete if not relevant.

| Host/profile | Default behavior | Rationale | Validation required |
|---|---|---|---|
| `windows_amd64_cpu` | `{default}` | CPU-safe baseline. | profile/unit/regression |
| `windows_arm64_cpu` | `{default}` | ARM64 CPU baseline. | profile/unit/regression |
| `windows_amd64_gpu_nvidia_cuda` | `{accelerated-default}` | CUDA-capable host. | profile/unit/regression/runtime if applicable |
| `windows_amd64_gpu_amd` | `{degraded-or-default}` | Pending/degraded accelerator path unless proven. | SKIP/PASS reason required |
| `windows_amd64_gpu_intel` | `{degraded-or-default}` | Pending/degraded accelerator path unless proven. | SKIP/PASS reason required |
| `windows_arm64_gpu_qualcomm_adreno_opencl` | `{arm64-default}` | OpenCL/Adreno path must not overclaim. | ARM64 evidence required |
| `windows_arm64_npu_qualcomm_qnn` | `{degraded-or-default}` | QNN proof in one family does not imply proof in another. | ARM64 evidence required |

---

## Slice-Level Closeout Criteria

All of these must be true:

1. The new mechanism is implemented through the existing repository architecture rather than a parallel path.
2. All new policy/config/settings values are validated by focused tests.
3. Runtime/setup behavior is observable through status, readiness, logs, script output, or tests.
4. Default setup remains simple for the user.
5. Explicit/full-catalog or advanced validation remains available where applicable.
6. Operator-facing controls are curated-first where the user should not edit raw values directly.
7. Raw overrides remain available when operationally necessary.
8. No new generated artifacts or large external artifacts are committed unless explicitly required.
9. Host-specific degraded or skipped states are explicit and not reported as PASS.
10. Focused tests pass before closeout.
11. `scripts/validate_backend.py profile`, `unit`, and `regression` pass on the implementing host.
12. `SYSTEM_INVENTORY.md` is updated only after both Windows AMD64 and Windows ARM64 verification exists, unless the user explicitly approves a narrower inventory state.

---

## Documentation and Governance Policy

- `CHANGE_LOG.md`: append only after validation. Include exact command, outcome, host class, and minimal evidence excerpt/report path.
- `SYSTEM_INVENTORY.md`: update only after the capability is verified on both Windows AMD64 and Windows ARM64, unless the user explicitly approves a narrower inventory state. Do not log planned capability.
- `docs/QuickStart.md`: update only when user-facing setup or normal operation changes.
- `README.md`: update only when project-level capability wording changes.
- Completed slice docs belong under `docs/slices-done/` when implementation and governance closeout are complete.
- If implementation diverges from this plan, update the slice doc before continuing.
- Use append-only corrections for governance files; do not rewrite history.

---

## Risks and Sequencing Notes

| Risk | Severity | Mitigation |
|------|----------|------------|
| Default setup becomes broader or slower | High | Make selected/current-host behavior the default and require explicit full-catalog behavior for broader validation. |
| A placeholder is mistaken for implemented capability | High | Mark placeholders/degraded states explicitly and block inventory promotion until proof exists. |
| Operator UX exposes raw implementation details first | Medium | Add curated controls and group raw overrides under Advanced. |
| Host-specific capability overclaims AMD64/ARM64 parity | High | Require separate host-class validation and log SKIP/PASS truthfully. |
| New code forks an existing runtime/setup path | High | Integrate through existing modules and tests; reject parallel managers or launchers. |

---

## Finish Line

Slice {Group} is complete when {capability} is implemented through the existing repository architecture, observable through validated status/readiness/setup/test evidence, and documented without overclaiming future or host-specific capability. `CHANGE_LOG.md` records the exact validation evidence. `SYSTEM_INVENTORY.md` is updated only after both Windows AMD64 and Windows ARM64 verification exists, unless the user explicitly approved a narrower inventory state.
