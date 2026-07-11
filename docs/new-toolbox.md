# New Toolbox — Pluggable Extensions Architecture

> This document is a transformation guide, NOT completion evidence.

## User Summary

JARVIS should gain new capabilities without requiring core code changes for every installation.

The target experience is:

1. Copy a standards-shaped extension into `data/extensions/<shape>/`.
2. Add only the local JARVIS settings that the extension requires.
3. Start or refresh JARVIS.
4. JARVIS discovers, validates, and reports the extension.
5. Valid capabilities become available through the existing application paths.

The three extension shapes are intentionally separate:

- **MCP** provides callable tools and related protocol capabilities.
- **Skills** provide reusable instructions, workflows, references, scripts, and assets.
- **Agents** provide delegated actors through an agent-card and task/message contract.

JARVIS keeps one runtime toolbox for callable tools, but the wider extension system may also contain skills and agents. Existing backend code remains the foundation: the current registry, executor, turn engine, agent specs, agent policy, dry-run roles, ledger, and API surfaces should be extended rather than replaced.

Filesystem access is limited to folders explicitly selected by the user. Each selected folder is read-only or read-write.

---

## 1. Objective

Transform the current tool and agent scaffolds into a pluggable extension system that follows shared agentic-development shapes instead of a JARVIS-only plugin format.

The target architecture must:

- preserve `ToolRegistry -> ToolExecutor -> TurnEngine`;
- preserve the existing `backend/app/agents` scaffold;
- use MCP as the first external tool-provider shape;
- use Agent Skills conventions for skills;
- use an agent-card plus task/message model for external agents;
- discover installed extensions from the canonical `data/` root;
- separate portable extension metadata from JARVIS-local state;
- permit additional extension shapes without replacing the toolbox;
- enforce filesystem roots and read/write level at execution;
- prefer modifying existing backend modules over creating parallel frameworks.

---

## 2. Core Concepts

- **Extension shape**: an external interoperability format, such as MCP, Agent Skills, or an agent-card protocol.
- **Provider**: the adapter that exposes one extension source to JARVIS.
- **Toolbox**: the aggregate callable tool surface presented to `ToolExecutor` and `TurnEngine`.
- **Skill catalog**: metadata and progressive loading for installed skills.
- **Agent catalog**: internal and external agent descriptions available for status, selection, and later delegation.
- **Tool**: one callable operation exposed by a provider.
- **Agent**: a delegated actor that receives tasks/messages and returns status, artifacts, or results. An agent is not a tool.

```text
Installed extensions
  ├─ MCP servers
  ├─ Skills
  └─ External agents
          │
          ▼
Existing and shape-specific loaders/adapters
          │
          ├─ Tool providers -> ToolRegistry -> ToolExecutor -> TurnEngine
          ├─ Skill catalog -> planning/agent context
          └─ Agent catalog -> existing agent policy/ledger/API -> future delegation runtime
```

---

## 3. Governing Migration Rule

Migration must prefer **use and modification of existing backend scaffolding** over redesign or broad refactoring.

Required approach:

1. Extend existing interfaces where they already own the behavior.
2. Add adapters at external-format boundaries.
3. Preserve existing data and API contracts unless interoperability requires a narrow additive field.
4. Avoid duplicate registries, duplicate ledgers, alternate agent runtimes, or a second tool execution path.
5. Move files only when the move is required for runtime ownership; do not reorganize merely for visual symmetry.
6. Keep compatibility shims while callers migrate, then remove them only under a separately validated change.

Existing authorities to retain:

- `backend/app/tools/registry.py` remains the callable toolbox.
- `backend/app/cognition/executor.py` remains the tool execution coordinator.
- `backend/app/conversation/engine.py` remains the canonical turn path.
- `backend/app/agents/specs.py` remains the internal agent-spec loader and validator.
- `backend/app/agents/policy.py` remains the agent enablement and allowed-role/tool gate.
- `backend/app/agents/ledger.py` remains the durable agent trace/event store.
- Existing planner, executor, critic, curator, learner, and creator modules remain the role scaffold.
- `backend/app/api/routes/agents.py` remains the agent status/trace API owner.

---

## 4. Directory Ownership

### 4.1 Backend code

Use the existing domains first. Add only the smallest adapter surfaces needed.

```text
backend/app/
├─ tools/
│  ├─ registry.py               # existing toolbox; extend for providers
│  ├─ provider.py               # small common ToolProvider contract if needed
│  ├─ models.py                 # normalized definitions/results if needed
│  ├─ system/                   # retain existing built-ins
│  ├─ search/                   # retain existing search tool
│  └─ filesystem/               # retain and expand existing filesystem tools
├─ agents/
│  ├─ specs.py                  # retain internal JarvisAgentSpec catalog
│  ├─ roles.py                  # retain role projection
│  ├─ policy.py                 # retain enablement/allow rules
│  ├─ messages.py               # extend toward interoperable task/message fields
│  ├─ ledger.py                 # retain trace/event persistence
│  ├─ planner.py                # retain dry-run planner scaffold
│  ├─ executor.py               # retain dry-run tool decision scaffold
│  ├─ critic.py
│  ├─ curator.py
│  ├─ learner.py
│  ├─ creator.py
│  ├─ discovery.py              # add external-agent directory discovery
│  ├─ cards.py                  # add agent-card normalization/validation
│  └─ provider.py               # add external-agent adapter only when execution is enabled
└─ extensions/                  # add only shared cross-shape coordination if proven necessary
   ├─ discovery.py
   ├─ models.py
   ├─ mcp/
   └─ skills/
```

Do not move the existing `backend/app/agents` implementation beneath a new framework. External-agent support should enter through adapters owned by that package.

### 4.2 Installed and user-managed content

```text
data/extensions/
├─ mcp/
│  └─ <installation>/
│     ├─ server.json
│     └─ jarvis.json            # optional local state
├─ skills/
│  └─ <skill-name>/
│     ├─ SKILL.md
│     ├─ scripts/               # optional
│     ├─ references/            # optional
│     └─ assets/                # optional
└─ agents/
   └─ <agent-id>/
      ├─ agent-card.json
      └─ jarvis.json            # optional local state
```

Use lowercase directory names: `mcp`, `skills`, and `agents`.

### 4.3 Existing internal agent content

Existing repo-owned agent specs and prompts remain in place:

```text
config/agents/specs/*.yaml
config/prompts/agents/*.md
```

They are internal JARVIS agent definitions, not installed external-agent packages. They should be represented in the same normalized agent catalog through an adapter, not physically moved into `data/extensions/agents`.

---

## 5. Toolbox Contract

### 5.1 Provider contract

The smallest useful tool-provider contract is:

```python
class ToolProvider(Protocol):
    provider_id: str

    def list_tools(self) -> list[ToolDefinition]: ...

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
    ) -> ToolCallResult: ...
```

Initial providers:

- built-in JARVIS tools;
- MCP servers.

The registry must not import arbitrary Python copied into `data/`.

### 5.2 Normalized tool definition

Use an MCP-compatible shape:

```python
@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, object]
    title: str | None = None
    output_schema: dict[str, object] | None = None
    annotations: dict[str, object] | None = None
```

### 5.3 Normalized result

```python
@dataclass(frozen=True, slots=True)
class ToolCallResult:
    content: list[ToolContent]
    structured_content: dict[str, object] | None = None
    is_error: bool = False
```

`ToolExecutor` may keep its current turn-facing `ToolResult`, normalizing provider results into that existing artifact contract.

### 5.4 Tool identity

Use provider-qualified routing identity:

```text
<provider-id>::<tool-name>
```

Examples:

```text
builtin::time
builtin::hardware.info
filesystem::read_file
github::get_issue
```

Existing unqualified names may remain as aliases during migration. Routing and artifacts must retain provider identity.

### 5.5 Registry responsibilities

Extend `backend/app/tools/registry.py` to own:

- provider registration;
- compatibility registration for existing `ToolBase` instances;
- deterministic listing;
- provider-qualified lookup;
- alias collision detection;
- invocation routing;
- provider identity in results;
- unavailable-provider reporting.

It must not own MCP transport, filesystem containment, skill loading, or agent delegation.

---

## 6. Existing Built-In Tools

Retain the existing modules and adapt them into one built-in provider:

- `time`;
- `hardware.info`;
- `search`;
- expanded filesystem operations.

Do not relocate or rewrite these tools merely to create a new directory layout. A small `BuiltinToolProvider` may wrap existing `ToolBase` objects.

Application startup should construct one registry, register the built-in provider, attach enabled MCP providers, store the registry on application state, and pass the same registry to every `TurnEngine` created by startup or session binding.

---

## 7. MCP Extension Shape

Each immediate child beneath `data/extensions/mcp/` is one installed MCP integration.

```text
data/extensions/mcp/<installation>/
├─ server.json                  # portable standards-shaped metadata
└─ jarvis.json                  # optional JARVIS-local state
```

Discovery:

1. Scan immediate child directories deterministically.
2. Require and validate `server.json`.
3. Load optional `jarvis.json`.
4. Skip disabled entries explicitly.
5. Start or connect to enabled servers.
6. Perform MCP initialization.
7. call `tools/list`.
8. Register returned tools under the provider identity.
9. Refresh when the server reports tool-list changes.
10. Isolate failures to the affected provider.

Application startup owns active MCP sessions. Application shutdown closes them. They are not recreated per turn.

---

## 8. Filesystem Access

Filesystem access is authorized only through user-selected roots.

Each root has:

- stable local id;
- `file://` URI;
- optional display name;
- `read-only` or `read-write` access.

`read-only` permits listing and reading. `read-write` additionally permits directory creation, file creation, and explicit overwrite.

Initial scope excludes delete, rename/move, execution, permission changes, link creation, and unrestricted binary editing.

JARVIS must enforce root containment and access before forwarding a filesystem MCP call or executing a built-in filesystem operation:

```text
call
  -> identify provider and operation
  -> resolve selected root
  -> resolve relative path
  -> verify target remains under root
  -> reject symlink/junction/reparse escape
  -> verify read/write level
  -> execute or forward
  -> normalize result
```

Create and overwrite are distinct intents. Create fails when a target exists. Overwrite fails when the target is absent unless a later contract explicitly changes that behavior.

---

## 9. Skills Shape

Follow the Agent Skills directory convention:

```text
data/extensions/skills/<skill-name>/
├─ SKILL.md
├─ scripts/                     # optional
├─ references/                  # optional
└─ assets/                      # optional
```

Discovery is metadata-first:

1. Discover immediate child directories.
2. Require `SKILL.md`.
3. Validate frontmatter.
4. Catalog name, description, and path.
5. Load full instructions only when selected.
6. Load scripts, references, and assets only as needed.

A skill is not automatically a tool. It may declare or describe dependencies on toolbox tools, including MCP tools.

---

## 10. Industry-Aligned Agent Shape

### 10.1 Conceptual external contract

External agents should use an **agent card plus task/message lifecycle** rather than a JARVIS-only YAML package.

The normalized agent card should be able to represent common industry fields:

```python
@dataclass(frozen=True, slots=True)
class AgentCard:
    agent_id: str
    name: str
    description: str
    version: str | None
    endpoint: str | None
    capabilities: dict[str, object]
    skills: list[dict[str, object]]
    input_modes: list[str]
    output_modes: list[str]
    authentication: dict[str, object] | None
    metadata: dict[str, object]
```

The exact wire adapter may target an A2A-compatible Agent Card and task/message exchange. JARVIS should normalize external cards instead of copying their fields into `JarvisAgentSpec` directly.

### 10.2 Installation unit

```text
data/extensions/agents/<agent-id>/
├─ agent-card.json              # portable external description
└─ jarvis.json                  # optional local state
```

`jarvis.json` may contain:

- enabled state;
- local display alias;
- endpoint override;
- environment/secret references;
- timeout and connection settings;
- mapping to permitted JARVIS roles or tools where needed.

Portable card metadata remains untouched.

### 10.3 Internal and external agents share a catalog, not a file format

The agent catalog should contain normalized entries from two sources:

```text
InternalAgentAdapter
  -> existing JarvisAgentSpec objects

ExternalAgentAdapter
  -> discovered AgentCard objects

Both
  -> AgentCatalogEntry
```

Suggested normalized entry:

```python
@dataclass(frozen=True, slots=True)
class AgentCatalogEntry:
    agent_id: str
    source: Literal["internal", "external"]
    display_name: str
    description: str
    enabled: bool
    capabilities: dict[str, object]
    allowed_tools: list[str]
    endpoint: str | None
    raw_reference: str
```

This allows common status and selection while preserving source-specific contracts.

### 10.4 Existing scaffold mapping

Use the current implementation as follows:

- `JarvisAgentSpec` remains the internal spec model.
- `load_agent_specs()` remains the internal catalog source.
- `roles.py` continues projecting internal role definitions.
- `AgentPolicy` remains the gate for whether roles/tools are allowed.
- `messages.py` is extended additively to represent task id, status, artifacts, and external message references when required.
- `AgentLedger` remains the durable record of plans, policy decisions, task events, outcomes, and external delegation records.
- Existing planner/executor/critic/curator/learner functions remain dry-run role implementations until a later slice enables live execution.
- The creator continues producing internal disabled specs; it does not create external agent cards.
- `/agents/status` expands to include normalized internal and external catalog entries.
- `/agents/traces/{trace_id}` continues reading the same ledger.

### 10.5 Discovery without execution

The first external-agent increment should provide discovery and status only:

1. Scan immediate children of `data/extensions/agents/`.
2. Require `agent-card.json`.
3. Validate and normalize the card.
4. Load optional `jarvis.json`.
5. Record readiness and reason.
6. Add valid entries to the agent catalog.
7. Expose them through the existing agent status API.
8. Do not delegate tasks until an execution slice explicitly enables it.

This uses the current read-only agent boundary rather than creating a second runtime.

### 10.6 Later delegation path

When live external-agent execution is approved, extend the existing path:

```text
agent request
  -> existing AgentPolicy
  -> normalized agent catalog lookup
  -> external-agent adapter
  -> task/message exchange
  -> existing AgentLedger records
  -> existing status/trace API
```

Do not route delegated agents through `ToolRegistry` as though they were tools. An agent may consume tools, and a tool may proxy a remote service, but those are separate contracts.

---

## 11. Application Wiring

Startup should:

1. construct the built-in tool provider;
2. discover and connect enabled MCP providers;
3. build one application-owned `ToolRegistry`;
4. discover skills into a separate skill catalog;
5. load existing internal agent specs;
6. discover external agent cards;
7. build one normalized agent catalog;
8. retain existing agent policy and ledger ownership;
9. store toolbox, catalogs, and readiness state on application state;
10. pass the same toolbox to every canonical `TurnEngine`;
11. close active provider/agent connections during shutdown.

No parallel conversation path or agent-only tool execution path should be introduced.

---

## 12. Readiness and Observability

For every extension installation, report:

- shape;
- installation id;
- source directory;
- enabled state;
- discovery and validation state;
- connection state where applicable;
- exposed capability count;
- reason when unavailable.

For tools, retain provider id, tool name, schema, annotations, and availability.

For agents, retain source, agent id, display name, capabilities, enabled state, endpoint availability, and reason.

Failures are localized. One broken MCP server, skill, or agent card must not remove valid built-ins or unrelated extensions.

---

## 13. Functional Boundaries

- Do not import arbitrary Python from installed data directories.
- Validate portable metadata before starting or connecting.
- Keep active processes/sessions application-owned.
- Preserve provider and agent source identity in artifacts and ledger records.
- Enforce filesystem containment and access at execution.
- Keep secrets outside portable manifests.
- Restrict discovery to declared roots.
- Keep MCP tools, skills, and agents as separate shapes.
- Avoid speculative authorization frameworks beyond concrete functional gates.
- Do not enable autonomous or external-agent execution as a side effect of discovery.

---

## 14. Migration Sequence

### Phase 1 — Complete the existing toolbox

- Extend `ToolRegistry` with provider routing while retaining `ToolBase` compatibility.
- Add normalized definitions/results only where required.
- Wrap existing tools in a built-in provider.
- Wire one registry through application startup and session binding.

### Phase 2 — Add MCP providers

- Add deterministic `data/extensions/mcp` discovery.
- Implement MCP lifecycle and tool normalization.
- Preserve existing executor, turn results, and artifacts.

### Phase 3 — Expand filesystem capability

- Reuse `backend/app/tools/filesystem`.
- Replace the single-root assumption with user-selected roots.
- Add read-only/read-write enforcement and operation-specific tools.
- Support both built-in and MCP filesystem providers through the same root authority where practical.

### Phase 4 — Add skills discovery

- Add metadata-first discovery beneath `data/extensions/skills`.
- Keep skills separate from tool registration.

### Phase 5 — Normalize the existing agent catalog

- Add `AgentCatalogEntry` or equivalent without replacing `JarvisAgentSpec`.
- Adapt existing specs into normalized catalog entries.
- Extend existing `/agents/status` output additively.
- Keep all existing agents disabled/dry-run according to policy.

### Phase 6 — Add external-agent discovery

- Discover `agent-card.json` beneath `data/extensions/agents`.
- Normalize cards into the same catalog.
- Record readiness through existing status surfaces.
- Do not implement live delegation yet.

### Phase 7 — Enable delegation separately

- Extend existing policy, messages, ledger, and role boundaries.
- Add an external-agent transport adapter.
- Validate task lifecycle, cancellation, artifacts, failures, and trace persistence.
- Enable only through an explicitly approved execution slice.

---

## 15. Acceptance Criteria

The transformation is complete when:

- existing built-in tools run through one provider-based toolbox;
- every canonical engine receives the same toolbox;
- valid copied MCP installations expose tools without core registration edits;
- invalid MCP providers fail independently;
- filesystem roots enforce read-only/read-write and containment;
- copied skills are metadata-discoverable without becoming tools;
- existing internal agent specs appear in a normalized agent catalog without being moved or rewritten;
- copied external agent cards appear in the same catalog without enabling execution;
- existing agent policy, dry-run roles, ledger, status, and trace APIs remain authoritative;
- later delegation can be added by extending those existing surfaces rather than creating a parallel agent framework;
- all tool calls still flow through the existing executor/turn/artifact path;
- all agent events and outcomes still flow through the existing ledger/status/trace path.

---

## 16. Non-Goals

- Marketplace implementation.
- Automatic installation from untrusted metadata.
- Arbitrary Python plugin imports.
- A replacement conversation engine.
- Rewriting the existing agent package.
- Moving internal agent specs into the external installation directory.
- Treating skills or agents as tools.
- Enabling autonomous or remote-agent execution during discovery work.
- Unrestricted host filesystem access.
- Deletion or execution in the initial filesystem capability.
- Replacing MCP or agent-card protocols with JARVIS-specific wire formats.
- Forcing built-in tools through local JSON-RPC.

---

## 17. Final Target

```text
data/extensions/
  ├─ mcp/       copied MCP integrations
  ├─ skills/    copied Agent Skills directories
  └─ agents/    copied external agent-card integrations

backend/app/tools/
  └─ existing toolbox extended with provider routing

backend/app/agents/
  └─ existing internal scaffold extended with external discovery and later delegation adapters

backend/app/extensions/
  └─ only shared cross-shape discovery/readiness code that is proven necessary
```

The governing principle is:

> Preserve JARVIS's existing execution and agent scaffolds. Add standards-shaped adapters at their edges so external tools, skills, and agents can be installed and shared without turning the application into a second, custom ecosystem.
