# New Toolbox — Pluggable Extensions Architecture

## User Summary

JARVIS should use a toolbox that can grow without requiring changes to the core application each time a new capability is added.

A new tool source should be installable by copying a standards-shaped directory into a designated data folder. JARVIS should discover it, validate it, expose its available tools, and route calls through the existing conversation and execution path.

The system should support multiple extension shapes rather than treating everything as one custom tool type:

- MCP servers provide callable tools and related protocol capabilities.
- Skills provide reusable instructions, workflows, references, scripts, and assets.
- Agents will eventually provide delegated actors through a separate interoperable contract.

JARVIS keeps one toolbox for runtime use, but that toolbox is assembled from multiple providers. Built-in tools and installed MCP servers appear through the same callable interface. Filesystem access is limited to folders explicitly selected by the user, with each folder marked read-only or read-write.

The intended operator experience is simple:

1. Copy an extension directory into `data/extensions/<shape>/`.
2. Configure any required local values in the extension's JARVIS sidecar file.
3. Start or refresh JARVIS.
4. JARVIS discovers the extension and reports whether it is ready.
5. Its tools become available through the normal toolbox when valid and enabled.

---

## 1. Objective

Transform the current tool registry into a pluggable, provider-based toolbox that follows established agentic coding ecosystem shapes rather than a JARVIS-only plugin format.

The target architecture must:

- preserve the existing `ToolRegistry -> ToolExecutor -> TurnEngine` execution path;
- support built-in tools and externally installed tool providers;
- use MCP as the first external tool-provider shape;
- reserve separate extension namespaces for skills and agents;
- discover installed extensions from the canonical `data/` root;
- keep portable extension metadata separate from JARVIS-specific local state;
- permit new extension shapes later without redesigning the toolbox;
- gate host filesystem access to user-designated folders with explicit read-only or read-write access.

This document defines the conceptual and technical target. It is a transformation guide, not completion evidence.

---

## 2. Core Architectural Decision

JARVIS will distinguish between:

- **extension shape** — the external format or interoperability contract;
- **provider** — the runtime adapter that makes one extension source available to JARVIS;
- **toolbox** — the aggregate callable tool surface presented to JARVIS execution;
- **tool** — one callable operation exposed by a provider.

The toolbox is not itself a plugin format. It is the normalized runtime view over all active providers.

```text
Installed extensions
  ├─ MCP servers
  ├─ Skills
  └─ Agents (future)
          │
          ▼
Shape-specific discovery and adapters
          │
          ▼
Tool providers
  ├─ BuiltinToolProvider
  └─ MCPToolProvider
          │
          ▼
ToolRegistry (the toolbox)
          │
          ▼
ToolExecutor
          │
          ▼
TurnEngine and turn artifacts
```

This preserves direct in-process execution for built-in tools while allowing protocol-backed providers such as MCP.

---

## 3. Directory Ownership

### 3.1 Backend code

Backend code owns discovery, validation, lifecycle, adaptation, routing, and execution.

Recommended shape:

```text
backend/app/
├─ extensions/
│  ├─ discovery.py              # aggregate extension discovery
│  ├─ models.py                 # shared installed-extension status models
│  ├─ registry.py               # extension catalog, distinct from callable toolbox
│  ├─ mcp/
│  │  ├─ client.py              # MCP connection/session lifecycle
│  │  ├─ discovery.py           # MCP installation discovery
│  │  ├─ models.py              # MCP installation/runtime state
│  │  ├─ provider.py            # MCP tools exposed as ToolProvider
│  │  └─ roots.py               # filesystem root normalization and enforcement
│  ├─ skills/
│  │  ├─ discovery.py           # Agent Skills directory discovery
│  │  ├─ loader.py              # metadata-first, progressive skill loading
│  │  └─ models.py
│  └─ agents/
│     └─ ...                    # reserved until the agent contract is implemented
└─ tools/
   ├─ registry.py               # callable toolbox and provider routing
   ├─ provider.py               # common ToolProvider contract
   ├─ models.py                 # normalized tool definitions/results
   ├─ builtin/
   │  ├─ provider.py
   │  ├─ time_tool.py
   │  ├─ hardware_tool.py
   │  └─ search_tool.py
   └─ filesystem/
      └─ ...                    # optional built-in filesystem implementation
```

Exact file splitting should remain minimal. The required boundary is more important than the number of files.

### 3.2 Installed and user-managed content

Installed extensions belong under the existing canonical `data/` root:

```text
data/extensions/
├─ mcp/
│  ├─ filesystem/
│  │  ├─ server.json
│  │  └─ jarvis.json
│  └─ github/
│     ├─ server.json
│     └─ jarvis.json
├─ skills/
│  └─ code-review/
│     ├─ SKILL.md
│     ├─ scripts/
│     ├─ references/
│     └─ assets/
└─ agents/
   └─ ...                       # reserved; no active loader until implemented
```

Use lowercase directory names: `mcp`, `skills`, and `agents`.

### 3.3 Why `data/extensions/`

`data/extensions/` is the neutral installation root because MCP servers, skills, and agents are not all tools.

- MCP is a protocol-backed capability source.
- Skills are reusable workflows and supporting material.
- Agents are delegated actors.

The toolbox may consume capabilities from these sources, but the sources should not be forced into one JARVIS-specific tool package shape.

---

## 4. Toolbox Contract

### 4.1 Tool provider

A provider is the smallest abstraction needed to aggregate built-in and external tools.

Conceptual contract:

```python
class ToolProvider(Protocol):
    provider_id: str

    def list_tools(self) -> list[ToolDefinition]:
        ...

    def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, object],
    ) -> ToolCallResult:
        ...
```

Initial providers:

- `BuiltinToolProvider`
- `MCPToolProvider`

Possible later providers:

- remote HTTP provider;
- A2A agent proxy provider;
- provider supplied by another supported extension shape.

The registry must not assume that every provider is a Python subclass copied into `data/`.

### 4.2 Tool definition

Use an MCP-compatible normalized tool shape:

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

This maps directly to MCP and can be adapted to other model-provider function-calling formats.

### 4.3 Tool result

Use a structured result rather than arbitrary success strings:

```python
@dataclass(frozen=True, slots=True)
class ToolCallResult:
    content: list[ToolContent]
    structured_content: dict[str, object] | None = None
    is_error: bool = False
```

The existing `ToolExecutor` may continue to produce its current turn-facing `ToolResult`, but it should normalize from `ToolCallResult` rather than assuming every provider returns a plain string.

### 4.4 Registry identity

Tool names are not guaranteed to be globally unique across providers.

Use a provider-qualified internal identity:

```text
<provider-id>::<tool-name>
```

Examples:

```text
builtin::time
builtin::hardware_info
filesystem::read_file
github::get_issue
```

The registry may expose model-facing aliases, but routing and artifacts must retain provider ownership.

### 4.5 Registry responsibilities

`backend/app/tools/registry.py` becomes the toolbox and should own:

- provider registration;
- deterministic provider and tool ordering;
- tool catalog refresh;
- provider-qualified lookup;
- collision detection for aliases;
- normalized tool listing;
- invocation routing;
- explicit unavailable/disabled provider reporting;
- preservation of provider identity in results.

It should not own:

- MCP transport implementation;
- filesystem path enforcement;
- skill interpretation;
- agent delegation;
- dynamic import of arbitrary Python from `data/`.

---

## 5. Built-In Tools

Existing JARVIS tools become one provider rather than special registry cases.

Initial built-ins:

- current time;
- cached hardware information;
- configured internet search.

Conceptual registration:

```python
builtin_provider = BuiltinToolProvider(
    tools=[
        TimeTool(),
        HardwareTool(profile),
        SearchTool(settings),
    ]
)
registry.register_provider(builtin_provider)
```

Built-ins should use the same normalized definitions and results as MCP tools. This keeps the toolbox consistent and makes built-ins exportable later.

---

## 6. MCP Extension Shape

### 6.1 Installation unit

Each immediate child directory beneath `data/extensions/mcp/` is one installed MCP integration.

Required portable file:

```text
server.json
```

Optional JARVIS-local file:

```text
jarvis.json
```

Example:

```text
data/extensions/mcp/filesystem/
├─ server.json
└─ jarvis.json
```

### 6.2 `server.json`

`server.json` should remain standards-shaped and portable. It describes the MCP server identity, version, package or remote endpoint, transport, arguments, and required environment inputs.

JARVIS should consume the official schema rather than inventing a parallel manifest.

### 6.3 `jarvis.json`

`jarvis.json` stores host-specific installation state that should not modify portable MCP metadata.

Conceptual shape:

```json
{
  "enabled": true,
  "selectedPackage": 0,
  "environment": {
    "LOG_LEVEL": "info"
  },
  "roots": [
    {
      "id": "documents",
      "uri": "file:///C:/Users/example/Documents/JARVIS",
      "name": "Documents",
      "access": "read-write"
    },
    {
      "id": "reference",
      "uri": "file:///D:/Reference",
      "name": "Reference",
      "access": "read-only"
    }
  ]
}
```

Do not store secrets directly in this file. Secret values should continue to resolve through an approved local secret/environment mechanism.

### 6.4 Discovery

At startup or explicit refresh:

1. Scan only immediate child directories under `data/extensions/mcp/`.
2. Require one `server.json` per installation.
3. Validate portable metadata.
4. Load optional `jarvis.json`.
5. Skip disabled installations.
6. Report invalid installations explicitly without preventing unrelated providers from loading.
7. Start or connect to enabled MCP servers.
8. Perform MCP initialization.
9. Call `tools/list`.
10. Register the returned tools under the provider identity.
11. Refresh the provider catalog when the MCP server reports a tool-list change.

Discovery must be deterministic and fail locally. One broken extension must not erase the built-in toolbox or unrelated providers.

### 6.5 Lifecycle

The application startup state should own active MCP sessions so they are reused rather than recreated per turn.

Application shutdown should close MCP sessions and child processes cleanly.

Session binding may rebuild `TurnEngine`, but it must continue to receive the same application-owned toolbox.

---

## 7. Filesystem Access

### 7.1 User-designated roots

Filesystem access is authorized only through roots explicitly selected by the user.

Each root has:

- stable local identifier;
- `file://` URI;
- optional display name;
- access level: `read-only` or `read-write`.

No tool call may introduce a new root or arbitrary host absolute path.

### 7.2 Access levels

`read-only` permits:

- list directories;
- inspect metadata needed for listing;
- read supported files.

`read-write` permits all read-only operations plus:

- create directories;
- create supported files;
- explicitly overwrite supported files.

Initial scope excludes:

- delete;
- rename or move;
- execute;
- ownership or permission changes;
- symlink, junction, or reparse-point creation;
- unrestricted binary editing.

### 7.3 Enforcement boundary

JARVIS must enforce root and access restrictions before forwarding an MCP tool call. A third-party filesystem server is not the sole authority for JARVIS-selected access.

Required sequence:

```text
requested tool call
  -> identify provider and operation
  -> resolve selected root
  -> resolve requested relative path
  -> verify final target remains inside root
  -> reject symlink/junction/reparse escape
  -> verify root access permits operation
  -> forward call to provider
  -> normalize result
```

### 7.4 Operation intent

Write behavior must be explicit.

Recommended inputs distinguish:

- create new file;
- overwrite existing file.

A create request should fail when the target already exists. An overwrite request should fail when the target does not exist unless a later contract explicitly changes that behavior.

---

## 8. Skills Shape

Skills follow the Agent Skills directory convention:

```text
data/extensions/skills/<skill-name>/
├─ SKILL.md
├─ scripts/        optional
├─ references/     optional
└─ assets/         optional
```

Discovery should be metadata-first:

1. identify immediate child directories;
2. require `SKILL.md`;
3. load and validate frontmatter metadata;
4. retain path and summary in the skill catalog;
5. load full instructions only when selected;
6. load scripts, references, and assets only when required.

A skill is not automatically a callable tool. It may reference or require toolbox capabilities, including MCP tools.

Skills should have a separate catalog even if later orchestration makes them visible to planning or agent systems.

---

## 9. Agents Namespace

Reserve:

```text
data/extensions/agents/
```

Do not activate discovery or execution until an interoperable agent contract is selected and implemented.

The current internal JARVIS agent specifications remain under their existing configuration paths. They should not be moved merely to match the reserved installation namespace.

When external agents are implemented, evaluate industry agent-card and delegation protocols separately from MCP and skills.

---

## 10. Application Wiring

The application startup path should:

1. construct the built-in provider;
2. discover installed MCP integrations;
3. establish enabled MCP providers;
4. build one `ToolRegistry` toolbox;
5. store the toolbox and extension readiness state on application state;
6. pass the same toolbox to every `TurnEngine` created by startup or session binding;
7. close active provider resources during application shutdown.

The existing conversation path remains authoritative:

```text
TurnEngine
  -> ToolExecutor
  -> ToolRegistry
  -> selected ToolProvider
  -> tool call
  -> normalized result
  -> turn result and artifact
```

No parallel conversation or agent-only tool execution path should be introduced.

---

## 11. Readiness and Observability

Extension discovery must produce observable state.

For each installation, report at least:

- extension shape;
- installation identifier;
- enabled state;
- discovery state;
- validation state;
- connection/start state where applicable;
- number of available tools;
- reason when unavailable;
- source directory.

For each registered tool, preserve:

- provider identifier;
- tool name;
- description;
- input schema;
- output schema when available;
- annotations when available;
- current availability.

Failures must be localized and explicit. A broken MCP server should not silently disappear, and it should not prevent built-in tools from loading.

---

## 12. Security and Functional Boundaries

The objective is functional interoperability, not a broad policy framework. Enforcement should occur at concrete execution boundaries.

Required controls:

- do not import arbitrary Python from installed data directories;
- validate installation metadata before execution;
- keep provider processes and sessions application-owned;
- preserve provider identity in routing and artifacts;
- prevent path traversal and link/reparse escape;
- enforce read-only/read-write at filesystem execution;
- keep secrets outside portable manifests;
- limit discovery to declared installation roots;
- fail one provider independently from the rest of the toolbox.

Avoid speculative authorization layers that are not required to deliver these behaviors.

---

## 13. Transformation Sequence

### Phase 1 — Normalize the existing toolbox

- Add normalized tool definition and result types.
- Add the `ToolProvider` contract.
- Convert `ToolRegistry` into provider-based routing.
- Preserve compatibility with the existing executor and turn artifacts.

### Phase 2 — Convert built-in tools

- Add `BuiltinToolProvider`.
- Wire time, hardware information, and search.
- Construct the toolbox during application startup.
- Ensure session-bound engines retain the same toolbox.

### Phase 3 — Add MCP installations

- Add `data/extensions/mcp/` discovery.
- Validate `server.json`.
- Load optional `jarvis.json`.
- Establish MCP client/session lifecycle.
- Import `tools/list` into the toolbox.
- Route `tools/call` through `MCPToolProvider`.

### Phase 4 — Add filesystem roots

- Represent user-selected roots with `file://` URIs.
- Add read-only/read-write local state.
- Enforce root containment and operation access before forwarding calls.
- Validate multi-root behavior and Windows path edge cases.

### Phase 5 — Add skills discovery

- Add `data/extensions/skills/` discovery.
- Validate `SKILL.md` metadata.
- Implement progressive loading.
- Keep skills separate from callable tool registration.

### Phase 6 — Reserve agents cleanly

- Create or recognize `data/extensions/agents/`.
- Do not load or execute external agents yet.
- Define the agent interoperability contract in a later approved effort.

---

## 14. Acceptance Criteria

The transformation is functionally complete when:

- the application constructs one provider-based toolbox;
- existing built-in tools are invocable through that toolbox;
- every engine created by startup or session binding receives the same toolbox;
- copying a valid enabled MCP installation directory beneath `data/extensions/mcp/` makes its discovered tools available without changing core registration code;
- invalid or unavailable MCP installations are reported without disabling other providers;
- provider-qualified tool identities prevent ambiguous routing;
- MCP tool definitions and results are normalized without losing protocol fields needed for interoperability;
- user-selected filesystem roots support multiple folders;
- read-only roots reject mutating operations;
- read-write roots permit the explicitly supported create and overwrite operations;
- all filesystem operations remain inside their selected roots;
- skills copied beneath `data/extensions/skills/` are discoverable through `SKILL.md` metadata without being misregistered as tools;
- `data/extensions/agents/` remains a reserved, inactive namespace until an agent contract is implemented;
- tool calls and failures continue to flow through the existing executor, turn result, and artifact path.

---

## 15. Non-Goals

This transformation does not require:

- a marketplace;
- automatic package installation from untrusted metadata;
- arbitrary Python plugin imports;
- a new conversation engine;
- autonomous agent execution;
- treating skills as tools;
- treating agents as tools;
- unrestricted host filesystem access;
- deletion or execution through the initial filesystem capability;
- replacing MCP with a JARVIS-specific protocol;
- forcing built-in tools to communicate through local JSON-RPC.

---

## 16. Final Target

The final conceptual model is:

```text
data/extensions/
  ├─ mcp/       copied protocol integrations
  ├─ skills/    copied Agent Skills directories
  └─ agents/    reserved future delegated actors

backend/app/extensions/
  └─ shape-specific discovery, validation, lifecycle, and adaptation

backend/app/tools/
  └─ normalized provider-based toolbox used by JARVIS runtime execution
```

The governing principle is:

> Extensions keep their industry-standard shape. JARVIS adapters discover and normalize them. The toolbox presents one stable callable surface without making every extension conform to a custom JARVIS package format.
