# GitHub workflow

GitHub Issues and pull requests provide lightweight coordination. Repository truth and validation rules remain in `AGENTS.md` and the repository validation tooling.

## Issue model

- A parent issue coordinates one outcome requiring several child issues. It replaces a slice.
- Child issues hold focused work and replace sub-slices.
- Use GitHub sub-issues for hierarchy and dependencies for blocked-by relationships.
- Do not duplicate hierarchy, dependencies, or status in task lists.

## Issue forms

- **Parent outcome:** coordinate the integrated outcome and its completion.
- **Work:** deliver a planned implementation or repository change with its normal validation, usually in one pull request.
- **Bug fix:** correct known broken or regressed behavior with reproducible evidence.
- **Investigation:** research, reproduce, compare, or resolve an architectural decision.
- **Validation:** independently prove an existing result only when a separate host, hardware, service, operator, or integrated product path is required.

Ordinary tests and validation belong in the work issue. Create a separate validation issue only for exceptional independent proof.

## Labels

The label catalog is [`.github/labels.json`](labels.json):

- `bug`
- `type:outcome`
- `type:work`
- `type:investigation`
- `type:validation`
- `status:ready`
- `status:blocked`
- `agent:appropriate`
- `agent:human`
- `area:backend`
- `area:desktop`
- `area:docs`
- `area:runtime`
- `area:infra`

## Pull requests

- Create a draft PR only while implementation, validation, or review preparation remains incomplete.
- When the linked issue is complete, required validation has passed, and the branch is ready for review, create or promote the PR as ready.
- Keep the diff limited to the linked issue.
- Report exact validation commands, results, and host class.
- Record limitations without claiming unverified completion.
- Link the PR with a closing keyword only when it fully completes the issue.
