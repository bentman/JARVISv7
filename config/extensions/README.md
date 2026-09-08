# Extension Definitions

Application-owned extension defaults live under `config/extensions/` and are
durable, reviewed, and tracked in version control. Operator-authored additions
live under `data/extensions/` and are untracked runtime data; they may be lost
when the data directory is cleared. The application definition wins when an
operator definition uses the same family and ID.

Declarative definition families use one YAML file per entry with this shape:

```yaml
id: example-id
name: Example extension
version: 1.0.0
definition: {}
```

The `definition` mapping is family-specific. Optional fields are `enabled`,
`dependencies`, and untrusted `metadata`. Secrets must use a separate
credential reference and must not appear in definitions.

Supported definition directories are `acp`, `mcp`, `hooks`, `plugins`, and
`tools`. Definitions never grant authority by themselves; executable effects
require ADR 0005 capability registration, process boundaries, authorization,
approval where required, cancellation, and evidence.

Tool definitions use a fixed `command` list plus a mandatory `process` mapping;
they may optionally identify a `skill_id` and declared `script`. Plugin
definitions identify a local source directory and a non-empty `extensions`
list of bundled family, ID, and relative path entries.

MCP definitions may use stdio (with `command` and `process`) or streamable HTTP
(with `url`). `credential_ref` resolves an application-owned credential: HTTP
uses a bearer authorization header, while stdio uses an explicit environment
variable mapping through `env_passthrough`. MCP definitions may declare OAuth
authorization-code configuration; the Extensions panel drives the desktop/native
authorization flow (status, authorize, code exchange) without ever handling the
secret directly.
