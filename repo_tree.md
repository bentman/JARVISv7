# Repository Placement Guide

`repo_tree.md` answers one question: **where should repository content live?**

It is not an architecture specification, runtime inventory, implementation ledger, or validation record. Those details belong in `ProjectVision.md`, `SYSTEM_INVENTORY.md`, `CHANGE_LOG.md`, code, configuration, and focused documentation.

## Placement Rules

- Put executable application behavior under `backend/app/`.
- Put desktop-shell code under `desktop/`; do not duplicate backend behavior there.
- Put declarative repository-owned settings under `config/`.
- Put provisioning, validation, bootstrap, packaging, and operator utilities under `scripts/`.
- Put tests under `backend/tests/`, organized by test level and functional domain.
- Put mutable runtime state under `data/`, cache state under `cache/`, model artifacts under `models/`, generated reports under `reports/`, and managed executable sidecars under `runtimes/`.
- Put durable explanatory or decision material under `docs/`.
- Keep repository-wide governance and entry-point files at the root.
- Do not create new top-level directories when an existing domain already owns the content.
- Prefer the narrowest existing domain that accurately owns the responsibility.

## Top-Level Layout

```text
JARVISv7/
├─ backend/             # Python application code and tests
├─ cache/               # mutable cache/service state
├─ config/              # declarative repository-owned configuration
├─ data/                # mutable application state and persisted artifacts
├─ desktop/             # desktop product shell
├─ docs/                # durable documentation and decision records
├─ models/              # downloaded or generated model artifacts
├─ reports/             # generated validation, diagnostic, and benchmark output
├─ runtimes/            # managed executable runtime sidecars
├─ scripts/             # provisioning, validation, bootstrap, packaging, utilities
├─ .env.example         # operator environment template
├─ AGENTS.md            # repository-wide agent instructions
├─ CHANGE_LOG.md        # implementation and validation history
├─ docker-compose.yml   # local service composition
├─ ProjectVision.md     # product and architectural direction
├─ pyproject.toml       # Python package, dependency, and tooling configuration
├─ README.md            # informal project entry point
├─ repo_tree.md         # placement guide
└─ SYSTEM_INVENTORY.md  # observed system and capability inventory
```

## Backend Placement

```text
backend/
├─ app/
│  ├─ agents/           # application-agent policy, specs, and ledger boundaries
│  ├─ api/              # HTTP routes, schemas, dependencies, app assembly
│  ├─ artifacts/        # persisted session/turn artifact models and writers
│  ├─ cache/            # cache keys, clients, and access logic
│  ├─ cognition/        # prompt construction and response shaping
│  ├─ conversation/     # turn/session state and orchestration
│  ├─ core/             # shared settings, paths, logging, capability types
│  ├─ hardware/         # detection, profiling, preflight, provisioning decisions
│  ├─ memory/           # working, episodic, semantic, retrieval, write policy
│  ├─ models/           # model catalog and model-selection support
│  ├─ personality/      # personality schemas, loading, and policy
│  ├─ routing/          # runtime selection and routing decisions
│  ├─ runtimes/         # concrete STT, TTS, LLM, wake, and search runtimes
│  └─ services/         # application services coordinating domain boundaries
├─ tests/
│  ├─ fixtures/         # shared test inputs
│  ├─ unit/             # isolated deterministic tests
│  ├─ integration/      # multi-module tests without live hardware
│  └─ runtime/          # live hardware/runtime validation
└─ requirements.txt     # generated/derived dependency artifact when retained
```

### Backend Rule of Thumb

- Domain behavior belongs in its domain package.
- API routes should adapt requests and responses, not own business behavior.
- Services coordinate domains; they should not duplicate domain implementations.
- Runtime-specific code belongs under `backend/app/runtimes/<family>/`.
- Shared code belongs in `core/` only when it is genuinely cross-domain.

## Configuration Placement

```text
config/
├─ agents/              # application-agent policy and specifications
├─ app/                 # application policy and runtime profile configuration
├─ hardware/            # human-readable hardware prerequisites and notes
├─ models/              # model catalog and selection metadata
├─ personality/         # personality profiles
├─ prompts/             # prompt assets that are actually consumed
└─ search/              # search-service configuration
```

Configuration must be declarative. Generated state, downloaded assets, logs, caches, and runtime databases do not belong in `config/`.

## Mutable and Generated Content

```text
cache/                  # disposable cache/service state
data/                   # persistent application state and artifacts
models/                 # model binaries and downloaded assets
reports/                # generated reports and diagnostics
runtimes/               # managed executable runtime distributions
```

These directories must not contain source-of-truth application code.

## Desktop Placement

```text
desktop/
├─ src/                 # desktop UI and backend API client code
└─ src-tauri/           # native/Tauri shell integration
```

Desktop code owns presentation and native-shell integration. Conversation, memory, runtime selection, and other application behavior remain in the backend.

## Documentation Placement

- Root governance files apply repository-wide.
- `docs/` holds durable architecture notes, operational guides, decisions, and retained concepts.
- Historical material may live under `docs/archives/`.
- Temporary discovery/action documents may live at the root while active, then be removed or archived when no longer useful.

## Adding New Content

Before creating a file or directory:

1. Identify the responsibility it owns.
2. Place it in the existing domain that owns that responsibility.
3. Avoid duplicate authorities, parallel implementations, and speculative placeholders.
4. Add a new directory only when multiple related files require a durable domain boundary.
5. Update this guide only when placement rules or durable repository domains change.
