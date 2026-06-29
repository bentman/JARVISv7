# desktop/AGENTS.md

Applies to `desktop/**`. The root contract still applies.

## Desktop role

The desktop shell is the durable user surface. It is not the backend, not the runtime selector, and not the hardware authority.

Keep the desktop thin:

- call backend APIs through existing client boundaries
- show backend readiness/status truthfully
- surface degraded states visibly
- do not duplicate hardware profiling or runtime selection in UI code
- do not move conversation orchestration out of the backend

## Commands

Run desktop commands from the repo root using the prefix form:

- `npm --prefix desktop install`
- `npm --prefix desktop run dev`
- `npm --prefix desktop test`

Do not install Tauri globally for this repo. Use repo-local desktop dependencies.

Rust/Tauri prerequisites are host prerequisites, not repo vendored dependencies.

## Backend contract

If a desktop change needs backend behavior, update the backend contract explicitly rather than scraping logs, shelling out, or duplicating state locally.

Desktop code should treat backend state as authoritative for:

- readiness
- hardware profile summary
- selected runtime/model status
- resident voice lifecycle
- degraded/error states
- settings that the backend owns

Keep user-facing labels honest. Do not show a feature as available unless the backend reports it ready or intentionally degraded.

## Tauri boundary

Use `desktop/src-tauri/` for shell integration only:

- process lifecycle
- window/tray/hotkey integration
- platform bridge code
- backend launch/health coordination where already patterned

Do not place secrets in desktop source. Do not add broad filesystem or process permissions without approval and a validation plan.

## Validation

Minimum desktop validation for desktop-only changes:

- `npm --prefix desktop test`

If the change affects backend lifecycle, API contracts, readiness display, or resident voice behavior, also run the smallest relevant backend validation or focused test.

For live desktop voice/runtime proof, report the host class and exact live test command. Missing live hardware should be reported as `SKIPPED`, not converted into a fake pass.

Generated desktop output, `node_modules`, build output, and Tauri artifacts must not be committed unless explicitly requested.
