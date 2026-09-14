# ADR Boundary Cleanup (0001–0008)

## Context

MCP capability is functionally complete enough to close, but ADR 0006 cannot be marked
`Implemented` because hooks and plugins — unstarted work — live inside the same ADR.
The same shape blocks 0005 and 0007. This is not an implementation problem; it is a
documentation-structure problem, and it is the reason capabilities stall.

Four root causes, each verified against the repo:

1. **ADR granularity is a ProjectVision promise, not an architecture decision.**
   ADRs 0001–0007 map 1:1 onto the Seven Promises. A promise spans many independently
   finishable decisions, so a promise-sized ADR can only close when its *slowest* part
   closes. AGENTS.md:111 already says "One ADR owns one architecture decision" —
   0005 and 0006 violate the repo's own rule.

2. **Shared infrastructure is owned by a consumer.** `backend/app/actions/sessions.py`
   (`SessionManager`) is owned by 0005 but consumed by MCP (0006) and ACP (0007). So
   0005 cannot close until its consumers are done, and its consumers restate its
   contracts — the restatement AGENTS.md:112 forbids.

3. **Evidence is duplicated and perishable.** `npm --prefix desktop test` is cited as
   evidence in 5 ADRs, `desktop/tests/static.test.mjs` in 4, the `1562 passed` figure in
   2. One validator run makes several ADRs stale simultaneously. 0006 has been rewritten
   24 times, 0005 18 times.

4. **The template permitted the drift.** `docs/adr/0000-adr-template.md`'s Confirmation
   section is a loose bullet list. ADRs 0001–0004 independently settled on a disciplined
   three-list form (Implementation files / Test coverage / Validation commands, no run
   output) — and those four are the ones that are `Implemented` with `Follow-up: None`.
   ADRs 0005–0008 invented a prose form that embeds pass counts, timings, and report
   filenames — and those four are the ones that churn and cannot close.

**The fix is not a new format.** It is to restore the convention 0001–0004 already
prove works, split promise-sized ADRs into independently closeable decisions, and
tighten the template and rules so the drift cannot recur.

Intended outcome: every ADR owns one decision that can reach `Implemented` on its own
evidence, and MCP can be closed out without waiting on hooks, plugins, or a native
desktop session.

### Decisions already made

- **Numbering:** extend with 0009+. ADRs 0005–0008 keep their IDs and narrow in place;
  extracted capabilities become new ADRs. This preserves ~18 ADR references in
  `backend/app/`, `backend/tests/`, `desktop/src-tauri/src/lib.rs`, and
  `config/extensions/README.md`. No renumbering, no file moves.
- **Evidence:** cite durable targets, not run output. Perishable results live only in
  `reports/validation/`.
- **Closeout bar:** an ADR reaches `Implemented` on its own backend/contract evidence.
  Native operator validation is ADR 0008's own closeout obligation, stated once there —
  not carried as open Follow-up in three other ADRs.
- **Scope:** full sweep, 0001–0008.

## Target ADR map

| ID | Owns (one decision) | Target status |
|---|---|---|
| 0001 | Host truth, readiness, runtime selection | `Implemented` (unchanged) |
| 0002 | One interaction loop, turn/session ownership | `Implemented` (refs corrected) |
| 0003 | Model/application authority boundary | `Implemented` (stale claim corrected) |
| 0004 | Memory layers and lifecycle | `Implemented` (stale claim corrected) |
| 0005 | **Effect-class risk model + capability contract/registry/execution/audit** | `Implemented` |
| 0006 | **Extension family taxonomy + catalog/lifecycle + governed operations** | `Implemented` |
| 0007 | Agent identity, profiles, direct invocation | `Accepted` |
| 0008 | Operator surface: Advanced Controls shell + native validation obligation | `Accepted` |
| **0009** | Shared session lifecycle (`backend/app/actions/sessions.py`) | `Implemented` |
| **0010** | MCP connection boundary (transport, discovery, caching, classification) | `Accepted`, closeable |
| **0011** | MCP authorization (OAuth / RFC 9728, 8414, 9207, 8707) | `Accepted` |
| **0012** | Hooks and plugins | `Proposed` — blocks nothing |
| **0013** | ACP adapter (outbound + inbound bridge) | `Accepted` |

Extracting 0012 is the single change that unblocks MCP closeout.

## Plan

### Step 1 — Fix the template and the rules first

Everything after this is written to the new contract, so do this first.

**`docs/adr/0000-adr-template.md`** — replace the loose Confirmation bullets with the
three-list form that 0001–0004 already use verbatim:

```
## Confirmation

Implementation files:
- path/to/file.py

Test coverage:
- backend/tests/unit/.../test_x.py

Validation commands:
- backend/.venv/Scripts/python scripts/validate_backend.py unit
```

State explicitly in the template that Confirmation records **targets, not results**: no
pass counts, no timings, no `reports/validation/*` filenames, no per-test narrative.
Recorded runs belong in `reports/validation/`.

Add a Follow-up convention matching 0001–0004: when `Implemented`, the section reads
`None for this ADR.` plus one forward-looking paragraph naming what would require an
update versus a new/superseding ADR.

**`AGENTS.md`** — extend the existing ADR rules block (lines 110–120) with three rules:

- *Closeability*: an ADR owns one decision that can reach `Implemented` on its own
  evidence. If one part can be finished while another cannot, they are two ADRs.
- *Shared infrastructure*: infrastructure consumed by two or more ADRs is owned by its
  own ADR, not by its first consumer.
- *Evidence*: Confirmation cites durable files, test targets, and validator command
  classes. Perishable run output belongs in `reports/validation/`.
- *Closeout bar*: backend/contract evidence closes an ADR. Native operator validation is
  ADR 0008's obligation and is not carried as Follow-up elsewhere.

### Step 2 — Extract shared infrastructure (0009)

Create `docs/adr/0009-shared-session-lifecycle.md` from ADR 0005's
"Shared connection lifecycle" section (0005:71–83).

Owns: `SessionManager`/`SessionHandlers`, the dedicated-thread event loop, per-connection
locking, confirmed-teardown semantics, `_close_and_evict_if_confirmed`,
`SessionCallOutcomeUnknownError`, `close_prefix`, and bounded `shutdown`.
Test coverage: `backend/tests/unit/actions/test_sessions.py`.

Family-specific adapter behavior stays with 0010 (MCP) and 0013 (ACP), which reference
0009 by ID for the shared contract only. Delete the restated lifecycle prose from
0006:85 and 0007's ACP section; replace each with a one-line ownership reference.

Status `Implemented` — `test_sessions.py` already covers reuse, races, cancellation-
resistant handlers, bounded waits, confirmed teardown, retained failed closes, and
family-specific retry.

### Step 3 — Narrow 0005

Keep only: the risk→friction effect-class model, the operator-request authorization
rule, and the capability descriptor/registry/execution/cancellation/audit contract
(`backend/app/actions/contracts.py`, `backend/app/services/capability_service.py`,
`backend/app/actions/boundaries.py`, `data/actions/action-log.jsonl`).

Remove: the session-lifecycle section (→ 0009) and the `actions-panel.js` presentation
paragraph (→ 0008). Move Follow-up item 1 (operator-readable audit presentation) to
0008; delete Follow-up item 2 (native interaction evidence) per the closeout rule.

Rewrite Confirmation to the three-list form. Set status `Implemented`.

### Step 4 — Split 0006

**0006 keeps**: the extension family taxonomy, the "no extension shape gets a parallel
execution path" rule, catalog/declarative lifecycle (`backend/app/extensions/` descriptors,
discovery, storage, operator manifests), governed operations and assistant integration
(`backend/app/cognition/tool_policy.py`, `ExtensionRuns`), and the skill / local-tool
families. Status `Implemented`.

**→ `docs/adr/0010-mcp-connection-boundary.md`** from 0006:79–95: SDK-backed stdio and
streamable HTTP, paginated discovery, tool/resource/resource-template/prompt records,
list-change invalidation, discovery-snapshot caching, allowlists, effect classification,
Disconnect. References 0009 for lifecycle, 0011 for credentials.

**→ `docs/adr/0011-mcp-authorization.md`** from 0006:97–103: `mcp_oauth.py`,
protected-resource and authorization-server discovery, issuer validation, resource-bound
tokens, refresh, secret storage, Forget authorization.

**→ `docs/adr/0012-hooks-and-plugins.md`** from 0006:117 and Follow-up items 2–3.
Status `Proposed`. `backend/app/extensions/hooks.py` and `plugins.py` exist as
scaffolding; the decision on operator workflows, bundle removal, and remote sources is
not made. Nothing else depends on it closing.

**Desktop MCP/skill/tool workflows** (0006:105–115) → 0008.

### Step 5 — Populate 0010/0011 Follow-up from the MCP conformance audit

These are the real, evidenced gaps that determine when MCP actually closes. Record them
as Follow-up; do not fix code in this pass.

0010:
- A lost `subscriptions/listen` stream permanently disables snapshot invalidation.
  `_pump_list_changes` in `backend/app/extensions/mcp.py` catches `Exception` and
  returns; a live probe confirmed a 2026-07-28 connection delivers no `list_changed` to
  `message_handler` without an open listen stream. Correct the claim currently at
  0006:91 that a failed listen "leaves the notification path in place" — that holds only
  for pre-2026 connections.
- `ttlMs: 0` is treated as `unknown` (cached indefinitely) where the spec says
  immediately stale; absent and negative TTLs likewise. The SDK's list models default
  `ttl_ms=0`, so this is the common path, not an edge case.
- The subscription acknowledgment (`Subscription.honored`) is never inspected, so
  partially-honored filters silently leave lists with no invalidation signal.
- Per-page cache metadata is collapsed to page 1.
- `_list_all_optional` swallows every exception for resource templates with no
  descriptor-problem evidence.

0011:
- RFC 9207: `iss` absent is never rejected (the spec's MUST when
  `authorization_response_iss_parameter_supported` is true); comparison applies
  trailing-slash normalization the spec forbids; the recorded issuer comes from the PRM's
  `authorization_servers[0]` rather than the validated AS metadata document, and the two
  are never compared.
- RFC 8414 discovery in `_discover_authorization_metadata` appends the well-known suffix
  to a path-bearing issuer instead of inserting it, and tries 2 of the 3 required URLs.
- OAuth token refresh changes the credential-context hash, which empties the connection's
  operation list until rediscovery (`_mcp_credential_context_hash` /
  `_fresh_mcp_snapshot` in `backend/app/services/extension_runtime_service.py`).

### Step 6 — Split 0007 and narrow 0008

**0007 keeps** agent identity, profiles, direct invocation, `AgentRegistry`,
`agent-invoke-*` descriptors, isolation and MCP filtering.

**→ `docs/adr/0013-acp-adapter.md`**: outbound `backend/app/extensions/acp.py` and the
inbound `acp_server.py` bridge, connection identity, resume, ACP v2 conformance gap.
References 0009 for lifecycle and 0006 for adapter definitions. Its conformance gap stops
blocking agent closeout.

**0008 narrows** to the Advanced Controls layout/shell decision, and becomes the single
owner of native operator validation. It absorbs the operator-presentation follow-ups
moved out of 0005 and 0006.

> Deviation, stated deliberately: AGENTS.md:118 says to keep layout ADRs separate from
> behavior-defect fixes. 0008's defect fixes are already shipped and validated; creating
> a retroactive ADR for completed work adds process without decision value. Record them
> in 0008's Implementation as consequences of the remount, and note that future defect
> work gets its own record.

### Step 7 — Correct 0001–0004

Small and surgical; these are `Implemented` and structurally fine.

- **0003**: "Action governance has contract scaffolding … not yet the general
  model-callable execution path" is stale — 0005 made it the execution path. Correct it
  and point to 0005.
- **0004**: `TurnArtifact` "defines fields for future action proposals, authorization
  decisions, approvals, execution results, cancellations, and delegated runs" — those
  fields are populated now. Correct, and reconcile with the stale comment at
  `backend/tests/unit/artifacts/test_turn_artifact.py:202`.
- **0002 / 0004**: disambiguate `SessionManager`. Two classes share the name —
  `backend/app/conversation/session_manager.py` (0002/0004) and
  `backend/app/actions/sessions.py` (0009). Qualify every mention with its module path,
  including the bare "real SessionManager" at 0006:135.
- **All eight**: trim `Related:` to genuine ownership, dependency, supersession, or
  evidence links. It is currently 6-of-7 on most ADRs, which carries no signal.

### Step 8 — Add the status index

Create `docs/adr/README.md`: a table of ID | Title | Status | Owns (one line) |
Closeout bar. Nothing else.

Keep it strictly derived from the ADR headers — no progress narration, no percentages,
no task lists. It is an index, not a fourth tracking system. `repo_tree.md:114` already
places ADRs under `docs/`; no new directory and no placement-guide change is needed.

## Files

Edited: `docs/adr/0000-adr-template.md`, `docs/adr/0001`–`0008`, `AGENTS.md`.
Created: `docs/adr/0009-shared-session-lifecycle.md`, `0010-mcp-connection-boundary.md`,
`0011-mcp-authorization.md`, `0012-hooks-and-plugins.md`, `0013-acp-adapter.md`,
`docs/adr/README.md`.

No source, test, or config file changes. No ADR renumbering, so the ~18 ADR references in
`backend/app/actions/sessions.py`, `backend/app/extensions/acp.py`,
`backend/app/services/extension_runtime_service.py`, `backend/tests/`,
`desktop/src-tauri/src/lib.rs`, and `config/extensions/README.md` all remain valid —
except where they name a moved decision, which Step 9 catches.

## Verification

Docs-only: no test asserts ADR content (confirmed — `backend/tests/` and `desktop/tests/`
contain no `docs/adr` reference), so nothing can break at runtime. Verify the contract
instead:

1. **No perishable evidence survives.** Should return nothing:
   ```bash
   grep -rnE "[0-9]+ (passed|skipped)|in [0-9.]+s|reports.validation" docs/adr/
   ```

2. **Every ADR ID cited in source still resolves.** Cross-check each hit against
   `ls docs/adr/`:
   ```bash
   grep -rnoE "ADR [0-9]{4}" --include=*.py --include=*.js --include=*.rs --include=*.md . | grep -v "^./docs/adr/\|.venv\|node_modules"
   ```
   Any reference naming a decision that moved (e.g. a `sessions.py` comment citing ADR
   0005 for lifecycle) must be repointed to 0009 — the one source-comment change this
   plan permits.

3. **Every ADR has all template sections**, and each new ADR's Confirmation has exactly
   the three lists:
   ```bash
   for f in docs/adr/0*.md; do echo "$f: $(grep -c '^## ' $f)"; done
   ```

4. **No restated ownership.** Confirm `SessionManager` lifecycle prose appears only in
   0009, MCP transport prose only in 0010, OAuth prose only in 0011:
   ```bash
   grep -ln "SessionHandlers\|streamable_http_client\|exchange_code" docs/adr/
   ```

5. **Closeout actually works** — the point of the exercise. After the split, 0005, 0006,
   and 0009 should each read `Implemented` with `Follow-up: None for this ADR.`, and
   0010's Follow-up should contain only MCP conformance items, no hooks/plugins and no
   native-desktop item.

6. **Regression sanity**, since `docker-compose.yml` was previously deleted by a cleanup
   commit and broke a unit test:
   ```bash
   backend/.venv/Scripts/python scripts/validate_backend.py unit
   ```
   Expect the same result as the current baseline (1562 passed / 7 skipped on
   windows-amd64) — recorded here for this plan only, not in any ADR.
