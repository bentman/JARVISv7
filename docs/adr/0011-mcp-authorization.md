# 0011 - MCP Authorization

Date: 2026-09-14
Status: Accepted
Related: 0005, 0008, 0010

## Context and Problem Statement

A remote MCP server is an OAuth 2.1 protected resource. Reaching it requires discovering its authorization server, obtaining a token bound to that specific resource, storing the token safely, refreshing it, and removing it on operator request.

This is a separable decision from the connection boundary in ADR 0010: the protocol surface can be complete while authorization conformance is still being finished, and vice versa. Keeping them together prevents either from closing.

Stdio servers are out of scope for this flow. The MCP specification directs stdio implementations to take credentials from the environment instead.

## Decision Drivers

- A token must be bound to the MCP server it was issued for, so it cannot be replayed against a different resource.
- The client must not be tricked into sending an authorization code to the wrong authorization server.
- Tokens are secrets and belong in the encrypted operator secret store, never in a definition file.
- Removing local authorization must also end the connection holding the bearer header.
- The host cannot revoke authorization at a remote server; it must not claim to.

## Decision Outcome

JARVISv7 implements the authorization-code flow with PKCE against the authorization server discovered from the MCP server's protected-resource metadata, or against explicitly configured endpoints.

Tokens are resource-bound per RFC 8707 and persisted in the encrypted operator secret store. The connection resolves credentials when opening; missing OAuth authorization is refused rather than opening an unauthenticated connection. A stdio credential reference must be listed in the process environment allowlist, so the server cannot be started without the credential it requires.

"Forget authorization" is a local operation. It removes the stored token and pending flow and closes the cached connection so its bearer header cannot be reused. It does not revoke authorization at the remote server, and it does not report that it has.

## Consequences

Positive:
- Operators can connect to protected MCP servers without hand-configuring endpoints the server already advertises.
- A stolen or stale token has a bounded blast radius because it is audience-bound to one resource.
- Local authorization removal is honest about what it did and did not do.

Negative:
- Discovery depends on the remote server implementing RFC 9728 correctly.
- Unconfirmed teardown during Forget produces a partial-failure state the operator must understand.
- Full RFC 9207 mix-up protection requires metadata the current implementation does not yet read.

## Implementation

`backend/app/extensions/mcp_oauth.py` implements the authorization-code flow, state-bound single-use verifiers, protected-resource discovery with authorization-server and OpenID Connect metadata fallback, issuer validation when `iss` is supplied, resource-bound token requests, endpoint discovery or explicit endpoints, local callback handling, token refresh, and reconnect guidance for insufficient-scope challenges.

Tokens persist in the encrypted operator secret store. `ExtensionRuntimeService.mcp_credentials` resolves credentials when opening the connection. `POST /extensions/{extension_id}/oauth/complete` accepts the authorization code, state, and an optional `iss`.

Forget authorization removes the local stored token and pending flow and closes the cached connection. Unconfirmed teardown raises a partial-failure error through the existing route: local authorization was removed, but the connection may still be running. Repeated requests remain unconfirmed while ADR 0009's manager retains that resource and blocks new work.

Current issuer validation and authorization-server metadata discovery are narrower than the specification requires; both are recorded as Follow-up below.

ADR 0010 owns connection and protocol behavior. ADR 0009 owns teardown confirmation. ADR 0008 owns the operator credential and OAuth control surfaces.

## Confirmation

Implementation files:
- `backend/app/extensions/mcp_oauth.py`
- `backend/app/services/extension_runtime_service.py`
- `backend/app/api/routes/extensions.py`

Test coverage:
- `backend/tests/unit/extensions/test_mcp_oauth.py`
- `backend/tests/integration/test_mcp_http_auth.py`
- `backend/tests/integration/test_extension_runtime.py` for credential invalidation and for Forget closing the live session through the production route and real session manager, including repeated failed requests

Validation commands:
- `backend/.venv/Scripts/python scripts/validate_backend.py unit`
- `backend/.venv/Scripts/python scripts/validate_backend.py integration`

Live authorization-server round trips are not covered. A seeded token in the real encrypted store exercised Forget and status refresh; no external authorization server was contacted.

## Follow-up

Conformance gaps against the 2026-07-28 authorization specification:

- RFC 9207 issuer validation is incomplete in three ways. An absent `iss` is never rejected, where the specification requires rejection when the authorization server advertises `authorization_response_iss_parameter_supported`; that metadata field is not read. Comparison applies trailing-slash normalization, which the specification explicitly forbids in favor of simple string comparison. The recorded issuer is taken from the protected-resource metadata's `authorization_servers[0]` rather than the `issuer` value in the validated authorization-server metadata document, and the two are never compared - the specification requires rejecting metadata whose `issuer` does not match the identifier used to construct its URL.
- RFC 8414 discovery in `_discover_authorization_metadata` appends the well-known suffix to the issuer instead of inserting it before the issuer's path component, and tries two of the three required URLs. Issuers with a path component - tenant- or realm-scoped authorization servers - will fail discovery.
- OAuth token refresh empties the connection's operation list until rediscovery. `_mcp_credential_context_hash` hashes the raw stored secret, which changes on refresh, so `_fresh_mcp_snapshot` discards the private snapshot. A refreshed token is the same authorization context, and the specification permits reuse within it.

Operator-facing credential and OAuth presentation is owned by ADR 0008.
