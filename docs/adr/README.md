# Architecture Decision Records

One ADR owns one architecture decision and must be independently closeable: it reaches
`Implemented` on its own evidence. See the ADR rules in `AGENTS.md` and the shape in
`0000-adr-template.md`.

This index is derived from the ADR headers. It records status and ownership only.
Evidence lives in each ADR's Confirmation section; recorded validation runs live in
`reports/validation/`.

| ID | Title | Status | Owns | Closeout bar |
|---|---|---|---|---|
| [0001](0001-know-the-machine.md) | Know the Machine | Implemented | Host truth, readiness, runtime selection | Met |
| [0002](0002-one-honest-interaction-loop.md) | One Honest Interaction Loop | Implemented | Turn/session ownership, one voice+text loop | Met |
| [0003](0003-mind-with-boundaries.md) | Mind with Boundaries | Implemented | Model/application authority boundary | Met |
| [0004](0004-memory-with-meaning.md) | Memory with Meaning | Implemented | Memory layers, curation, lifecycle | Met |
| [0005](0005-governed-ability-to-act.md) | Governed Ability to Act | Implemented | Effect-class risk model, capability contract, execution, audit | Met |
| [0006](0006-ways-to-extend-assistant-ability-to-act.md) | Ways to Extend Assistant Ability to Act | Implemented | Extension taxonomy, catalog, governed operations, skills, local tools | Met |
| [0007](0007-extend-assistant-when-stable.md) | Extend Assistant When Stable | Accepted | Agent identity, invocation modes, agent scope | Profile management and non-direct invocation modes |
| [0008](0008-operator-experience.md) | Operator Experience | Accepted | Advanced Controls shell, all operator surfaces, native validation | Native desktop session validation |
| [0009](0009-shared-session-lifecycle.md) | Shared Session Lifecycle | Implemented | Connection reuse, teardown confirmation, shutdown | Met |
| [0010](0010-mcp-connection-boundary.md) | MCP Connection Boundary | Accepted | MCP transport, discovery, cache freshness, effect classification | 2026-07-28 conformance gaps in Follow-up |
| [0011](0011-mcp-authorization.md) | MCP Authorization | Accepted | MCP OAuth discovery, tokens, refresh, forget | RFC 9207/8414 conformance gaps in Follow-up |
| [0012](0012-hooks-and-plugins.md) | Hooks and Plugins | Proposed | Hook and plugin contracts | Decision not yet made; blocks nothing |
| [0013](0013-acp-adapter.md) | ACP Adapter | Accepted | Outbound and inbound Agent Client Protocol | ACP v2 conformance |

## Ownership boundaries worth knowing

- **Native operator validation is ADR 0008's alone.** No other ADR carries it as
  follow-up; backend and contract evidence closes those ADRs.
- **Shared infrastructure has its own ADR.** ADR 0009 owns connection lifetime because
  both ADR 0010 (MCP) and ADR 0013 (ACP) consume it.
- **Two classes are named `SessionManager`.** `backend/app/conversation/session_manager.py`
  is conversation session state (ADR 0002, ADR 0004).
  `backend/app/actions/sessions.py` is connection lifecycle (ADR 0009).
- **ADR 0012 blocks nothing.** Hooks and plugins were extracted from ADR 0006 so that
  undecided work stops holding completed families open.
