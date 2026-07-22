# GitHub workflow scaffold

This repository uses GitHub Issues and pull requests as lightweight work-management surfaces. The goal is to support clear assignment, review, and validation without replacing the repository’s existing truth sources in AGENTS.md, backend/AGENTS.md, and scripts/validate_backend.py.

## Workflow model

- Use parent issues for coordination when several sub-issues contribute to one meaningful outcome.
- Use sub-issues for focused, assignable work.
- Use one implementation issue per focused PR.
- Use labels for type, readiness, area, and agent suitability.
- Keep the project board optional; issues remain the source of truth for active work.

## Suggested labels

- type:investigation
- type:decision
- type:implementation
- type:validation
- status:ready
- status:blocked
- agent:appropriate
- agent:human
- area:backend
- area:desktop
- area:docs
- area:runtime
- area:infra

## Suggested project statuses

- Proposed
- Ready
- Assigned
- In Review
- Blocked
- Verified

## Issue usage guidance

- Investigation issues should gather evidence and recommend a direction.
- Decision issues should resolve a concrete architecture or workflow choice.
- Implementation issues should define one observable outcome and one focused PR.
- Validation issues should independently prove an integrated result.

## PR usage guidance

- Link the PR to the issue using a closing keyword only when the PR fully satisfies that issue.
- Report exact validation commands and results.
- Keep the diff limited to the assigned outcome.
- Do not claim completion without evidence.
