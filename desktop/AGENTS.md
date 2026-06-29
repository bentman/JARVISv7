# desktop/AGENTS.md

Applies to `desktop/**`. The root contract still applies.

## Role

The desktop shell is the durable user surface. It is a thin Tauri adapter over the backend API, not the backend, not the runtime selector, and not the hardware authority.

Keep the desktop thin:

- call backend APIs through existing client boundaries
- show backend readiness/status truthfully
- surface degraded states visibly
- do not duplicate hardware profiling or runtime selection in UI code
- do not move conversation orchestration out of the backend
- do not scrape logs or shell out to infer state that belongs in an API contract

`scripts/run_jarvis.py` is a developer/proving-host diagnostic path. Do not treat it as the desktop shipping surface.

## Host prerequisites

Desktop work requires repo-local Node/npm dependencies plus the host's Tauri prerequisites.

Windows x64:

- Rust stable toolchain
- Node.js LTS
- MSVC C++ build tools through Visual Studio or Build Tools
- WebView2 runtime where the OS does not already provide it

Windows ARM64:

- Rust stable toolchain
- Node.js LTS, native ARM64 preferred where available
- MSVC C++ ARM64 build tools
- WebView2 runtime

Cross-compiling x64 to ARM64 is an escape hatch, not the primary dev path. If used, make the target and validation host explicit.

## Commands

Run desktop commands from the repo root using the prefix form:

- `npm --prefix desktop install`
- `npm --prefix desktop test`
- `npm --prefix desktop run dev`
- `npm --prefix desktop run build`

Do not install Tauri globally for this repo. Use repo-local desktop dependencies.

## Backend contract

Desktop code should treat backend state as authoritative for:

- health/readiness
- hardware profile summary
- selected runtime/model status
- resident voice lifecycle
- degraded/error states
- settings that the backend owns
- agent/tool/status surfaces exposed by backend routes

If a desktop change needs new backend behavior, update the backend API/schema explicitly and validate both sides.

Keep user-facing labels honest. Do not show a feature as available unless the backend reports it ready or intentionally degraded.

## Tauri boundary

Use `desktop/src-tauri/` for shell integration only:

- process lifecycle
- window/tray/hotkey integration
- platform bridge code
- backend launch/health coordination where already patterned

Do not place secrets in desktop source. Do not add broad filesystem, shell, or process permissions without approval and a validation plan.

## Layout expectations

Keep UI code under `desktop/src/` and shell bridge code under `desktop/src-tauri/`. Avoid moving backend policy into either location.

Generated desktop output, `node_modules`, build output, and Tauri artifacts must not be committed unless explicitly requested.

## Validation

Minimum desktop validation for desktop-only changes:

- `npm --prefix desktop test`

If the change affects backend lifecycle, API contracts, readiness display, settings, resident voice, or agent/status surfaces, also run the smallest relevant backend validation or focused test.

For live desktop voice/runtime proof, report the host class and exact live test command. Missing live hardware should be reported as `SKIPPED`, not converted into a fake pass.
