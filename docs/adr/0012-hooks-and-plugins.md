# 0012 - Hooks and Plugins

Date: 2026-09-14
Status: Proposed
Related: 0005, 0006, 0008

## Context and Problem Statement

ADR 0006 defines hooks and plugins as extension families: hooks are deterministic actions tied to known lifecycle events, and plugins are installable packages that may bundle several extension shapes.

Scaffolding exists for both. `backend/app/extensions/hooks.py` supplies closed lifecycle event names, event recording, and governed capability dispatch. `backend/app/extensions/plugins.py` supplies bounded local installation, bundle hashing, and child-definition validation. Neither has an operator workflow, and neither has a decided contract for the questions that make them safe to expose.

These two families previously shared an ADR with MCP, skills, and local tools. That prevented completed families from being closed out while undecided ones remained open. This ADR exists so the undecided work has its own record and blocks nothing else.

## Decision Drivers

- Hooks execute local behavior on lifecycle events, so their event names, effects, and failure paths must stay small and visible.
- A hook that runs regardless of model choice is useful precisely because it is deterministic; that also makes a surprising hook hard to diagnose.
- Plugins are packaging and lifecycle, not a synonym for every capability they contain.
- Plugin removal must have a defined bundle-removal contract before removal is exposed, or an operator can leave orphaned child definitions behind.
- Remote plugin sources and arbitrary install scripts are a materially different trust decision from local installation.

## Decision Outcome

Not yet decided.

The open questions are:

- Which lifecycle events hooks may bind to, and whether that set stays closed.
- How a hook declares its effect class and reaches ADR 0005's governed execution path.
- How hook failures surface, and whether a failing hook can block the event it observes.
- What the plugin bundle-removal contract is, including child definitions, stored state, and credentials.
- Whether plugin install/enable/disable/remove/retire are distinct operator states or a smaller set.
- Whether remote sources and install scripts are in scope at all; if so, that requires a separate decision rather than an extension of local installation.

Until these are decided, hook and plugin scaffolding remains internal. No operator workflow is exposed, and no other ADR depends on this one closing.

## Consequences

Positive:
- ADR 0006 and the MCP ADRs can reach `Implemented` without waiting on undecided work.
- The undecided questions are recorded rather than living as follow-up bullets on an unrelated ADR.

Negative:
- Two extension families named in ADR 0006's taxonomy have no operator surface, so the taxonomy is broader than what an operator can currently use.
- The existing scaffolding may need to change once the contract is decided, so it should not accumulate dependents in the meantime.

## Implementation

Not implemented. Current scaffolding, which this ADR will either adopt or replace:

- `backend/app/extensions/hooks.py`: closed lifecycle event names, event recording, governed capability dispatch.
- `backend/app/extensions/plugins.py`: bounded local installation, bundle hashing, child-definition validation.

ADR 0006 owns the extension taxonomy and catalog these families are declared through. ADR 0005 owns governed execution for any hook or plugin behavior with effects. ADR 0008 owns operator workflows once they exist.

## Confirmation

Not applicable while status is `Proposed`.

Existing scaffolding coverage:
- `backend/tests/unit/extensions/test_hook_runner.py`
- `backend/tests/unit/extensions/test_plugin_installation.py`

## Follow-up

- Decide the hook contract: bindable events, effect declaration, failure surfacing, and whether a hook can block its event.
- Decide the plugin bundle-removal contract before exposing removal.
- Decide whether remote sources and install scripts are in scope; if so, record that as a separate decision.
- Add Hook creation/editing by event, effect, target, and arguments, with event history, failure visibility, and disable controls.
- Add local Plugin install/inspect/enable/disable/remove/retire workflows.
- Add backend validator and desktop contract evidence before moving this ADR past `Accepted`.
