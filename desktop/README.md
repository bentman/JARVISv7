# JARVISv7 Desktop Shell

Native desktop host built with Tauri 2.x. This is the **durable application
surface** for JARVISv7 from slice D.2 onward. The backend is unchanged; the
shell is a thin adapter over the backend API contract defined in D.1.

The proving host `scripts/run_jarvis.py` is a developer/diagnostic tool —
**not** the shipping path.

---

## Developer Prerequisites by Host Architecture

### Windows x64

- **Rust**: stable toolchain via [rustup](https://rustup.rs/).
- **Node.js**: LTS (x64 build).
- **MSVC v143 build tools**: install via Visual Studio 2022 or Visual
  Studio Build Tools; select the "Desktop development with C++" workload.
- **WebView2 runtime**: present on Windows 11 by default; on Windows 10
  install the Evergreen Bootstrapper from Microsoft if missing.

### Windows ARM64

- **Rust**: stable toolchain via rustup, plus the ARM64 target:
  ```
  rustup target add aarch64-pc-windows-msvc
  ```
- **Node.js**: LTS (ARM64 build where available; x64 Node runs via
  emulation but native is preferred).
- **MSVC v143 — VS 2022 C++ ARM64 build tools**: per Tauri's Windows
  installer docs, these are required to build for ARM64. Install via
  Visual Studio Installer — select "C++ ARM64 build tools" under the
  "Desktop development with C++" workload. The exact name is
  `MSVC v143 - VS 2022 C++ ARM64 build tools (Latest)`.
- **WebView2 runtime**: present on Windows 11 ARM64 by default.

### Cross-compile x64 → ARM64

Documented escape hatch, not the primary dev path:

```
tauri build --target aarch64-pc-windows-msvc --bundles nsis
```

The NSIS installer itself runs via emulation on ARM; the bundled
application is native ARM64.

---

## Layout (populated across slices D.1–D.5)

```
desktop/
├─ src/                       # web UI (vanilla JS or framework of choice)
│  ├─ assets/
│  ├─ components/
│  │  ├─ conversation/        # conversation display + tool-grounded response rendering (F.3)
│  │  ├─ hardware-selection/  # shows active family + device per STT/TTS/LLM/Wake
│  │  ├─ llm-selection/       # policy-gated runtime switcher (local/Ollama/cloud)
│  │  ├─ status/              # tray + in-window state display (12 canonical states)
│  │  └─ tray/                # system tray presence + state icons + context menu
│  ├─ index.html
│  ├─ main.js
│  └─ style.css
├─ src-tauri/
│  ├─ src/
│  │  ├─ backend.rs           # backend process lifecycle bridge
│  │  ├─ lib.rs               # Tauri app entry
│  │  ├─ main.rs
│  │  └─ tray.rs              # tray presence, state icons, context menu
│  ├─ Cargo.toml
│  ├─ build.rs
│  └─ tauri.conf.json
└─ README.md                  # this file
```

---

## Build & Run (populated across D.1–D.5)

Once the shell is implemented, standard Tauri commands apply:

- Dev: `cd desktop && pnpm tauri dev`
- Build (native): `cd desktop && pnpm tauri build`
- Build (cross x64 → ARM64): see Cross-compile section above.

No shell-side orchestration logic. All runtime selection, model acquisition,
and policy decisions live in `backend/app/**`. The shell calls the backend
API routes (`health`, `readiness`, `session`, `task`, `voice`, `diagnostics`,
`agents`) defined by slice D.1.
