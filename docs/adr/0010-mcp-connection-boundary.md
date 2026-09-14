# 0010 - MCP Connection Boundary

Date: 2026-09-14
Status: Accepted
Related: 0005, 0006, 0008, 0009, 0011

## Context and Problem Statement

Model Context Protocol provides a standard shape for connecting external capability. An MCP server may expose resources, prompts, and tools, but it does not receive blanket trust: JARVIS remains the host and controls discovery, connection lifecycle, consent, isolation, errors, and disconnection.

MCP is a connection boundary, not an agent. The architecture needs a decision for how an MCP server's advertised surface becomes discoverable operations, how that surface is classified for authorization, how cached discovery stays honest, and how the connection is ended.

This decision was originally recorded inside ADR 0006. It is extracted so MCP can be completed and closed independently of hook and plugin workflows, which are not started.

## Decision Drivers

- Server-declared metadata describes capability; it never grants authority.
- A cached discovery snapshot must not keep presenting operations the server no longer exposes.
- Effect classification must default to the safer class when server hints are missing or malformed.
- Stdio process boundaries apply regardless of what a tool claims about itself.
- Protocol and transport behavior belong here; connection lifetime belongs to ADR 0009.

## Decision Outcome

MCP connections are host-controlled. JARVIS opens them, holds them through ADR 0009's shared session lifecycle, classifies their operations by effect, and ends them on operator request.

Operation classification is `external_read` for discovery, resource reads, and prompt fetches on either transport. Tool annotations refine classification: boolean `destructiveHint: true` selects `destructive_action`; otherwise boolean `readOnlyHint: true` selects `external_read`. Missing or malformed hints retain the transport default - `privileged_execution` for stdio, `external_write` for HTTP. Destructive claims take precedence over conflicting read-only claims.

All MCP tool capabilities retain `requires_approval` for model proposals because server metadata cannot grant authority. Specific operator requests execute directly under ADR 0005, and stdio process boundaries remain enforced regardless of classification.

## Consequences

Positive:
- External capability can be added without a per-server trust model.
- A server cannot lower its own approval requirement through metadata.
- Cached discovery is invalidated by server announcement and by credential context, so the catalog does not silently misdescribe a connection.
- Stdio and streamable HTTP share one discovery, invocation, and evidence path.

Negative:
- Honest cache invalidation requires tracking freshness and credential context that the protocol only partially specifies.
- Conservative defaults mean an unannotated read-only tool is treated as privileged on stdio.
- Protocol revisions deliver list changes differently, so more than one notification path must be supported.

## Implementation

### Connections and discovery

`backend/app/extensions/mcp.py` implements SDK-backed stdio and streamable HTTP connections, paginated discovery, schema-preserving tool/resource/resource-template/prompt records, list cache metadata, allowlists, cancellation, and host callbacks. Absent or empty allowlists mean unrestricted access within the connection's other controls. Stdio definitions require explicit command, argv/environment allowlists, and working root.

Both transports attach to ADR 0009's shared session lifecycle. A stdio process stays open across discovery, tool calls, resource reads, and prompt fetches. Host elicitation context is rebound for each call. SDK connection-closed errors trigger cleanup and eviction; ordinary tool errors do not evict a healthy connection. The failed call is not replayed automatically; later use can open a replacement.

MCP uses the SDK's close path for both graceful and forceful termination. The manager awaits that single attempt, allowing the SDK's subprocess termination escalation to finish. Unconfirmed teardown remains tracked and subsequent Disconnect attempts remain unconfirmed; the adapter has no separate forceful retry beneath that path.

### Disconnection

`extension-mcp-disconnect`, exposed through `POST /extensions/{extension_id}/disconnect`, ends the held connection while preserving its definition, enablement, and credentials. Confirmed disconnection permits reopening on next use. An unconfirmed close raises instead of reporting success. Runtime detail reports `connected` separately from the cached discovery snapshot; a retained, unconfirmed resource remains connected in that accounting even though further calls are blocked.

### Discovery snapshot freshness

Discovery snapshots persist across backend restarts so operations remain discoverable. Restored health starts as unknown. Desktop shows "not connected" when live connection accounting is false, rather than presenting cached ready health as current.

A server-announced list change invalidates the cached snapshot. A `subscriptions/listen` stream pumps tool/resource/prompt change events on a 2026-07-28 connection; the SDK's message handler carries unprompted `notifications/*/list_changed` on a handshake-era connection. Either announcement drops that connection's snapshot from memory and `data/operator.sqlite`, so its discovered operations stop being presented until a later discover rebuilds both. The connection itself stays open.

Snapshots carry per-list `ttlMs`/`cacheScope` evidence and credential-context hashes. Positive TTLs that expire hide the affected dynamic operations until rediscovery. Private snapshots are reused only when the current credential context matches the stored hash. Invalid `x-mcp-header` tool metadata is filtered out with descriptor-problem evidence.

Current freshness handling does not yet match the specification for absent, zero, and negative TTLs, and a lost listen stream is not re-established. Both are recorded as Follow-up below.

### Boundaries owned elsewhere

ADR 0006 owns the extension catalog and definition lifecycle that MCP connections are declared through. ADR 0005 owns authorization, execution boundaries, and action evidence. ADR 0009 owns connection lifetime and teardown confirmation. ADR 0011 owns credentials and authorization challenges. ADR 0008 owns the operator-facing MCP workflows.

## Confirmation

Implementation files:
- `backend/app/extensions/mcp.py`
- `backend/app/services/extension_runtime_service.py`
- `backend/app/api/routes/extensions.py`

Test coverage:
- `backend/tests/unit/extensions/test_mcp.py`
- `backend/tests/integration/test_mcp_sdk.py`
- `backend/tests/integration/test_extension_runtime.py` for real stdio reuse and process death, Disconnect/reopen, a server that ignores SIGTERM, current-call elicitation ownership, and server-announced list changes on both the subscription and handshake-era notification paths

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration`

## Follow-up

Protocol conformance gaps against the 2026-07-28 specification, each verified against the installed SDK:

- A lost `subscriptions/listen` stream permanently disables snapshot invalidation. `_pump_list_changes` catches `Exception` and returns, with no re-listen. A live probe confirmed that a 2026-07-28 connection delivers no `list_changed` to `message_handler` without an open listen stream, so the message-handler path is not a fallback for that revision - it covers handshake-era connections only. The SDK raises `SubscriptionLost` for abrupt drops, ends the iterator on graceful server closure, and settles lost on event-buffer overflow; each currently ends invalidation for the life of the connection.
- `ttlMs: 0` is treated as unknown freshness and cached indefinitely, where the specification says immediately stale. Absent TTLs should default to `0`, and negative TTLs should be treated as `0`. The SDK's list-result models default `ttl_ms=0`, so this is the common path rather than an edge case.
- The subscription acknowledgment is never inspected. The server honors only the filter it acknowledges, so a partially-honored filter silently leaves some lists with no invalidation signal and no evidence that invalidation is unavailable.
- Per-page cache metadata is collapsed to the first page. The specification makes each page independently cacheable with its own freshness clock.
- `_list_all_optional` swallows every exception for resource templates, turning an authorization or transport failure into an empty list with no descriptor-problem evidence.

Operator-facing MCP presentation is owned by ADR 0008.
