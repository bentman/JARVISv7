# Issue-Based Work Assignment

Use GitHub Issues as the authority for active work.

```text
parent issue
  -> focused sub-issues
  -> dependencies
  -> one reviewable PR per implementation issue
  -> independent validation
  -> close and record verified results
```

Do not create dated task documents as a parallel work queue.

## 1. Work Types

Classify each issue before assignment.

| Type | Output | Code changes |
|---|---|---|
| Investigation | Evidence and recommendation | Normally no |
| Decision | Chosen contract or architecture boundary | Normally no |
| Implementation | One observable working result | Yes |
| Validation | Independent proof of an integrated result | Normally no |

Do not assign implementation while material facts or architecture choices remain unresolved.

## 2. Parent Issues

Create a parent issue when several tasks contribute to one meaningful outcome.

A parent issue should contain:

- the outcome;
- why it matters;
- current evidence;
- invariants that must remain true;
- explicit exclusions;
- integrated acceptance behavior;
- real GitHub sub-issues;
- blocking relationships.

A parent issue is coordination, not an agent task.

### Parent issue template

```markdown
## Outcome
[State the meaningful result without prescribing implementation.]

## Why
[State user value or engineering risk.]

## Current evidence
[Describe observed behavior and relevant repository paths.]

## Invariants
- [Behavior that must remain true]

## Out of scope
- [Adjacent capability not included]

## Integrated acceptance
[Describe the final observable scenario.]

## Sub-issues
Use GitHub sub-issues. Do not duplicate their status here.

## Completion
Close only after integrated acceptance is independently verified.
```

## 3. Assignable Sub-Issues

An implementation issue must define one independently provable result.

It is ready for assignment only when it has:

- one observable outcome;
- one primary product or runtime path;
- known scope;
- explicit exclusions;
- binary acceptance criteria;
- exact validation commands or interactions;
- resolved dependencies;
- no unresolved architecture decision;
- a change small enough for one focused PR.

### Implementation issue template

```markdown
## Outcome
[Observable behavior that must exist.]

## Current evidence
[What happens now, with relevant paths.]

## Required behavior
[What must change. Avoid unnecessary implementation prescription.]

## Product entry point
[API, desktop, CLI, startup, voice, text, or library path.]

## Scope
- [Relevant surfaces]

## Out of scope
- [Explicit exclusions]

## Acceptance criteria
- [ ] [Binary observable condition]
- [ ] [Failure or degraded behavior]
- [ ] [No-regression condition]

## Validation
[Exact focused commands and/or product interaction.]

## Dependencies
[Blocked by / blocks.]

## Agent instructions
- Inspect before editing.
- Follow `AGENTS.md` and any nearer scoped instructions.
- Keep the diff limited to this outcome.
- Report exact commands and observed results.
- Do not claim completion from tests alone when product-path proof is required.
- Do not broaden scope or close the issue.
```

## 4. Sizing Rule

A task is appropriately sized when all answers are yes:

- Can a reviewer decide pass or fail using one focused scenario?
- Can it merge without another unfinished PR?
- Does every changed file support one coherent outcome?
- Can it be reverted without undoing unrelated work?
- Can the diff be reviewed without reconstructing a large plan?
- Are all material design choices already settled?

A small diff is not necessarily a small task. A task may touch several files when every change is required for one observable result.

## 5. Lifecycle

1. Identify one meaningful outcome.
2. Inspect current behavior.
3. Create a parent issue only when coordination is needed.
4. Create focused sub-issues.
5. Add blocking relationships.
6. Mark an issue ready only when it is assignable without invention.
7. Assign one ready issue to one agent or human.
8. Produce one focused PR.
9. Review the complete diff.
10. Independently run the acceptance scenario.
11. Close only the issue fully satisfied by the PR.
12. Update `CHANGE_LOG.md` or `SYSTEM_INVENTORY.md` only with verified facts.

## 6. GitHub Setup

Minimum repository setup:

- enable GitHub Issues;
- use GitHub parent issues and sub-issues;
- use blocked-by and blocking relationships;
- link a PR with `Fixes #<issue>` only when the PR fully satisfies that issue;
- use labels for type, readiness, area, and agent suitability.

Suggested labels:

```text
type:investigation
type:decision
type:implementation
type:validation
status:ready
status:blocked
agent:appropriate
agent:human
area:<domain>
```

An optional GitHub Project may provide views and ordering. It is not a second source of truth.

Suggested Project fields:

```text
Status: Proposed | Ready | Assigned | In Review | Blocked | Verified
Type: Investigation | Decision | Implementation | Validation
Area
Priority
Agent suitability
```

Optional repository forms:

```text
.github/
  ISSUE_TEMPLATE/
    investigation.yml
    decision.yml
    implementation.yml
  pull_request_template.md
```

Keep forms short. Their purpose is to prevent missing outcome, scope, acceptance, and validation details.

## 7. Codex Cloud

Use Codex Cloud for repository tasks that have reproducible setup and validation.

Repository preparation:

- keep `AGENTS.md` concise and current;
- document deterministic setup and validation commands;
- identify commands safe in a cloud environment;
- identify hardware-dependent proof that cannot run in cloud;
- avoid placing active task plans in `AGENTS.md`;
- expose only required repositories and credentials;
- enable internet access only when the task requires it.

### Codex task prompt

```text
Work from GitHub issue #<number>.

Read the issue, AGENTS.md, any nearer scoped AGENTS.md, and directly relevant code before editing.
Implement only the issue's stated outcome.
Respect its scope, exclusions, dependencies, and acceptance criteria.
Run the focused validation listed in the issue.
Inspect the final diff for unrelated changes.

Return:
1. outcome achieved or not achieved;
2. files changed and why;
3. exact commands and results;
4. limitations or unverified behavior;
5. commit or PR for review.

Do not broaden the task, edit unrelated documentation, or mark the issue complete.
```

Good Codex Cloud tasks:

- report-only repository investigations;
- focused implementations with deterministic validation;
- request-flow tracing;
- tests for already-defined behavior;
- independent PR inspection.

Poor Codex Cloud tasks:

- broad requests such as `finish memory`;
- unresolved architecture decisions;
- tasks whose only proof requires unavailable hardware;
- several dependent implementations assigned in parallel;
- self-verification by the implementing agent as the sole completion evidence.

## 8. GitHub Copilot Free

Use Copilot Free as limited local assistance, not as the work-management system.

Suitable uses:

- inline completion;
- explaining selected code or an error;
- generating a small test or repetitive fragment;
- reviewing a selected block;
- drafting issue text for human review.

Do not depend on Copilot Free for:

- asynchronous issue-to-PR execution;
- repository-scale delegated implementation;
- high-volume PR review;
- persistent custom-agent workflows;
- the authoritative task queue.

The GitHub issue process must remain usable when AI quotas are exhausted.

## 9. Pull Requests

Default rule:

```text
one implementation issue -> one focused PR
```

Use a closing keyword only when the PR completely satisfies the linked issue.

### PR template

```markdown
## Linked issue
Fixes #[NUMBER]

## Outcome
[Observable behavior changed.]

## Changes
[Only changes required for the outcome.]

## Validation
- Command or interaction:
- Result:
- Host class:

## Boundaries
- Out-of-scope behavior unchanged:
- Hardware or service paths not validated:

## Review checklist
- [ ] No unrelated changes
- [ ] Acceptance criteria demonstrated
- [ ] Failure or degraded behavior explicit
- [ ] Documentation claims match observed behavior
```

## 10. Verification

The implementing agent's report is not the verdict.

The reviewer must:

- read the full diff;
- confirm every changed file supports the assigned outcome;
- run focused validation independently where practical;
- exercise the real entry point when tests are insufficient;
- inspect failure and degraded behavior;
- reject claims based on unverified assumptions;
- close only the specific issue fully satisfied.

## 11. Anti-Drift Rules

- A checked issue list does not prove completion.
- A passing unit test does not prove product-path behavior.
- A PR should not close multiple independently meaningful issues by default.
- Investigation issues do not produce production edits unless explicitly converted to implementation work.
- Agents do not silently expand scope.
- Current-state documentation is not updated from intention alone.
- Historical task documents are not active authority.
- GitHub Projects provide views; Issues remain the work authority.
- `CHANGE_LOG.md` and `SYSTEM_INVENTORY.md` record verified results, not plans.

## 12. Legacy Transition

1. Stop creating new dated execution-plan documents.
2. Do not migrate all historical plans into Issues.
3. Create Issues only for active or deliberately queued work.
4. Pilot the process with one current outcome.
5. Keep historical plans archived as history.
6. Link durable architecture decisions from parent issues when needed.
7. Remove or deprecate instructions that treat the legacy mechanism as active authority.
