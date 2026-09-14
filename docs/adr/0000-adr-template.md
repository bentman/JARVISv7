# 000N - Short Decision Title

Date: YYYY-MM-DD
Status: Proposed | Accepted | Implemented | Rejected | Superseded by 000X
Related: 000X, 000Y

## Context and Problem Statement

Why this decision exists. What problem, force, constraint, or architecture gap requires a choice now.

## Decision Drivers

- Driver 1
- Driver 2
- Driver 3

## Decision Outcome

State the decision directly.

Short rationale for why this decision was selected.

## Consequences

Positive:
- What becomes better or simpler.

Negative:
- What gets harder or constrained.

## Implementation

The architecture as implemented in the current codebase.

This section is mutable after implementation and later architecture changes. It should describe current ownership boundaries, main flows, contracts, and important files without becoming a code tour.

Describe contracts and boundaries, not line-level mechanics. Detail that changes whenever the code changes does not belong here; it goes stale between commits and makes the ADR untrustworthy.

## Confirmation

Confirmation records **evidence targets, not evidence results**. Use three lists:

Implementation files:
- `path/to/file.py`

Test coverage:
- `backend/tests/unit/.../test_x.py`

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `npm --prefix desktop test` for desktop contract changes
- `backend/.venv/Scripts/python scripts/validate_backend.py runtime --families ... --devices ...` for live host/device validation claims

Do not record pass counts, timings, skip counts, `reports/validation/*` filenames, or per-test narrative. Those are perishable: they make every ADR that cites them stale on the next run. Recorded runs live in `reports/validation/`.

Name the host class only when the decision itself is host-class specific.

## Follow-up

Only gaps required to finish this ADR while status is `Accepted`.

Once status is `Implemented`, this section reads:

```
None for this ADR.

Future <related work> should update this ADR when it preserves the same architecture,
or create/supersede an ADR when it changes the architecture.
```

Follow-up holds work that this ADR must finish. It does not hold general roadmap, work owned by another ADR, or obligations that belong to a consumer of this decision.

> Reference: https://adr.github.io/adr-templates/  
