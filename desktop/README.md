# JARVISv7 Desktop Shell

The desktop shell is the durable user-facing surface for JARVISv7. It is built with Tauri and stays intentionally thin: the backend owns hardware profiling, runtime selection, model readiness, policy, conversation orchestration, and durable state.

Use this folder for the native shell, UI presentation, tray/window behavior, hotkeys, and backend lifecycle bridge. Do not move backend policy or runtime decisions into desktop code.

For repo-wide setup, start with [docs/QuickStart.md](../docs/QuickStart.md). For desktop-specific contributor/agent rules, use [desktop/AGENTS.md](AGENTS.md).

## Commands

Run from the repository root:

```powershell
npm --prefix desktop install
npm --prefix desktop test
npm --prefix desktop run dev
npm --prefix desktop run build
```

Use repo-local desktop dependencies. Do not install Tauri globally for this repo.

## Host prerequisites

Desktop development requires Node.js/npm, Rust, the Tauri Windows prerequisites, and the relevant MSVC build tools for the target architecture.

Windows ARM64 work should prefer native ARM64 tooling when available. Cross-compiling from x64 to ARM64 is an escape hatch; make the target and validation host explicit when using it.

## Boundary

`scripts/run_jarvis.py` is a developer/proving-host diagnostic tool, not the shipping desktop path.

The desktop shell should call backend APIs through existing client boundaries and display backend-reported status truthfully. If the UI needs state the backend does not expose, add or update the backend API contract rather than scraping logs or duplicating runtime logic.

Generated desktop output, `node_modules`, build output, and Tauri artifacts should not be committed unless a task explicitly requires it.
