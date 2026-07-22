# GitHub workflow scaffold

This repository uses GitHub Issues and pull requests as lightweight work-management surfaces. The goal is to support clear assignment, review, and validation without replacing the repository’s existing truth sources in AGENTS.md, backend/AGENTS.md, and scripts/validate_backend.py.

## Workflow model

- Use parent issues for coordination when several sub-issues contribute to one meaningful outcome.
- Use GitHub-native sub-issues for focused, assignable work.
- Use GitHub-native issue dependencies for blocked-by and blocking relationships.
- Use one implementation issue per focused PR.
- Use labels for type, readiness, area, and agent suitability.
- Keep the project board optional; issues remain the source of truth for active work.

## Parent, sub-issue, and dependency workflow

- Create a parent issue when several tasks contribute to a single meaningful outcome.
- Keep the parent body focused on outcome, invariants, and integrated acceptance.
- Break the work into GitHub sub-issues rather than duplicating hierarchy in issue bodies.
- Use GitHub issue dependencies for blocked-by and blocking relationships.
- Do not duplicate hierarchy or dependency state inside issue text when GitHub already tracks it natively.

## Suggested labels

The repository includes a minimal label set in [.github/labels.json](labels.json) for the workflow scaffold. Create or import these labels in the repository settings before using the templates.

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
- For partial or follow-up work, link the issue without closing it.
- Report exact validation commands and results.
- Keep the diff limited to the assigned outcome.
- Do not claim completion without evidence.

## Projects

GitHub Projects are optional for this repository. Use them only if the maintainers want a board-style view for triage or sprint planning. They are not a second source of truth; issues and PRs remain the source of truth for active work.
