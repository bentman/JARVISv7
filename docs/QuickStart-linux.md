# Quick Start — Linux / WSL

> **Verified scope:** Linux AMD64 NVIDIA CUDA has a managed llama.cpp production path, and the existing Tauri desktop shell now has a build and backend-lifecycle proof under WSL2/WSLg. WSL2 is the proving environment, not a separate runtime identifier. This guide does not claim native-Linux coverage beyond that host, completed audio turns, wake detection, STT/TTS inference, or non-CUDA accelerator support.

This guide parallels the Windows repo-run desktop preview flow using Bash and Linux-style paths. Run commands from the repository root, and do not install Python packages globally.

## Prerequisites

Backend setup:

- A supported Linux distribution or WSL 2
- Bash and Git
- Python `>=3.11,<3.14` with `venv` support
- Internet access for dependency and model acquisition

WSL2 needs a few host-specific setup choices, especially around Python.  
See [Appendix 2: WSL2 host setup](#appendix-2-wsl2-host-setup) before creating the repo environment.

Desktop shell:

- Node.js and npm
- Rust toolchain
- C/C++ build tools and `pkg-config`
- GTK 3, WebKitGTK 4.1, JavaScriptCoreGTK 4.1, OpenSSL, librsvg, and Ayatana AppIndicator development packages
- A working graphical session; WSL additionally needs WSLg or another supported display path

The current Ubuntu 22.04/WSLg proving host built Tauri 2 with these package-level prerequisites:

```text
build-essential pkg-config curl wget file
libssl-dev libgtk-3-dev libwebkit2gtk-4.1-dev
libayatana-appindicator3-dev librsvg2-dev
```

Optional local services:

- Docker Engine and the Compose plugin for Redis and SearXNG (optional)

## Clone

```bash
git clone https://github.com/bentman/JARVISv7.git
cd JARVISv7
```

For an existing clone:

```bash
cd <REPO_ROOT_PATH>
git pull
```

## Before you touch config or dependencies

Three rules prevent the most common self-inflicted setup problems:

- **`pyproject.toml` is the only place Python dependencies are declared.** `backend/requirements.txt` is *generated* from it by `scripts/provision.py lock` (base extra only) and is read by tooling, not by you. Never hand-edit it — regenerate it instead if it's ever out of sync.
- **`.env` overrides `.env.example` key-by-key, not wholesale.** Both files are loaded; `.env` values win only for the keys they actually set. Leaving a key out of `.env` means the `.env.example` (or hardcoded) default still applies. Never edit `.env.example` for local changes — copy it to `.env` first.
- **Not all settings are meant to be touched.** `backend/app/core/settings.py` classifies every setting as `primary`, `advanced`, `derived`, `services`, `secret`, `compatibility`, or `test-only`. Stick to `primary` settings (see below) unless you have a specific reason to go further:

  | Class | Meaning | Examples |
  |---|---|---|
  | `primary` | Safe, expected day-to-day toggles | `USE_LOCAL_MODEL`, `LLM_MODEL_MODE`, `USE_OLLAMA`, `USE_SEARXNG` |
  | `advanced` | Path/tuning overrides, rarely needed | `LLAMA_CPP_MODEL_PATH`, `LLAMA_CPP_TIMEOUT_SECONDS` |
  | `derived` | Computed from a `primary` setting unless explicitly set | `LOCAL_MODEL_FETCH`, `LLAMA_CPP_MANAGED` |
  | `services` | Only matters if the optional Docker service is running | `REDIS_PORT`, `SEARXNG_PORT` |
  | `secret` | Credentials | `TAVILY_API_KEY` |
  | `compatibility` / `test-only` | Legacy or CI-only | `JARVISV7_OLLAMA_URL`, `JARVISV7_LIVE_TESTS` |

## Repo-run desktop preview

Use this path for the normal product-preview flow:

```text
prepare shell -> create backend venv -> bootstrap -> install desktop deps -> launch desktop
```

The desktop shell starts the backend, creates or resumes a session, loads readiness, starts the resident voice stream when available, and displays backend, readiness, service, wake, resident voice, and session state.

### 1. Prepare Bash

```bash
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8
repo_root="$(git rev-parse --show-toplevel)"
export TEMP="$repo_root/cache/temp"
export TMP="$repo_root/cache/temp"
export TMPDIR="$repo_root/cache/temp"
export PIP_CACHE_DIR="$repo_root/cache/pip"
export HF_HOME="$repo_root/cache/huggingface"
mkdir -p "$TEMP" "$PIP_CACHE_DIR" "$HF_HOME"
```

### 2. Create the backend environment

Prefer Python 3.13 when available:

```bash
/usr/local/bin/python3.13 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
```

Fallback if needed:

```bash
/usr/local/bin/python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
```

> Use `backend/.venv/bin/python` for the validated Linux AMD64 CUDA path.

### 3. Use starter settings

For first setup, leave `.env.example` defaults in place and just copy it:

```bash
cp .env.example .env
```

Starter defaults:

```text
USE_LOCAL_MODEL=true
LLM_MODEL_MODE=dev
LLM_MODEL_POLICY=auto
LLM_MODEL_ID=
USE_OLLAMA=false
USE_SEARXNG=false
USE_DDGS=true
```

Keep `LLM_MODEL_ID` blank unless you intentionally want an explicit model override. A nonblank `LLM_MODEL_ID` wins over dev/prod policy selection.

Normal JARVIS Ollama turns use the structured `/api/chat` path. The direct `/api/generate` adapter remains only for direct-prompt compatibility.

Ollama requests keep the selected model resident for `5m` by default. Set the advanced `OLLAMA_KEEP_ALIVE` value in `.env` to another Ollama duration when needed.

### 4. Bootstrap backend dependencies and models

```bash
backend/.venv/bin/python scripts/bootstrap.py
```

Bootstrap runs five checkpoints in order and stops at the first failure:

| # | Checkpoint | What it does |
|---|---|---|
| 1 | `profile` | Detects host hardware (CPU/GPU/NPU, architecture) |
| 2 | `provision` | Runs `scripts/provision.py install` to resolve and install hardware-appropriate extras from `pyproject.toml` |
| 3 | `ensure_models` | Runs `scripts/ensure_models.py` to acquire or verify STT, TTS, wake, and LLM model artifacts |
| 4 | `preflight` | Probes STT/TTS/LLM/wake readiness and reports probe status |
| 5 | `validate_profile` | Runs `scripts/validate_backend.py profile` as a final sanity check |

If it fails, use the reported checkpoint name and reason to run the corresponding repository command for a fuller error.

Wake support remains evidence-dependent. On the current WSL2 proving host, OpenWakeWord imported, reported ready, and its monitor ran over the resident stream. That establishes startup and monitoring only; it does not validate wake detection or a completed voice turn on Linux.

### 5. Install desktop dependencies and launch

```bash
npm --prefix desktop install
npm --prefix desktop test
npm --prefix desktop run dev
# npm --prefix desktop run build
```

Do not install Tauri globally for this repo. Use repo-local desktop package commands.

The running desktop is the main product-preview surface. Use its readiness, services, resident voice, wake, session, and error panels before dropping to backend scripts.

On the current WSL2/WSLg proving host, the shell built and launched, started the backend through `backend/.venv/bin/python scripts/run_backend.py`, created a session, loaded readiness, and polled the consolidated desktop status API. Audio inference and completed resident voice turns remain unvalidated.

For a compile-only proof before opening a window:

```bash
cargo check --manifest-path desktop/src-tauri/Cargo.toml
npm --prefix desktop run build
```

The WSLg proof emitted two non-fatal GTK scale-factor diagnostics during startup. They did not terminate the shell or prevent the frontend/backend lifecycle. Tray construction completed, but WSLg tray presentation was not separately confirmed.

## Model acquisition

`scripts/ensure_models.py` manages four independent model families: `stt`, `tts`, `wake`, and `llm`. Bootstrap acquires all of them; you only need this section if one family fails or you want to manage it directly.

```bash
backend/.venv/bin/python scripts/ensure_models.py --family llm --verify-only
backend/.venv/bin/python scripts/ensure_models.py --family stt --verify-only
backend/.venv/bin/python scripts/ensure_models.py --family tts --verify-only
backend/.venv/bin/python scripts/ensure_models.py --family wake --verify-only
```

Drop `--verify-only` to acquire a missing or mismatched artifact for that family.

Some catalog entries are not plain downloads — the catalog can mark an entry `pending-pinned-release`, `pending-viability`, or `build-required`. If a family fails to resolve and the error references one of these, that model needs manual build or export steps rather than a retry.

## Hardware acceleration

Linux AMD64 NVIDIA CUDA is verified for the managed llama.cpp sidecar: b9704 / commit `10786217e9d40c848ac0133cbe9c5f22a52421bb` / build 9704, using `/usr/local/cuda-12.4` and `runtimes/llama.cpp/linux-amd64-cuda`. The live proof starts the managed sidecar, exercises health/models/completion, confirms CUDA offload, and leaves no `llama-server` process. See [Linux llama.cpp CUDA build](helpers/jarvis-wsl-llamacpp.md).

ROCm, Vulkan, OpenCL, other Linux accelerator paths, and Linux desktop/audio behavior remain outside this verified claim.

Useful intended diagnostics:

```bash
backend/.venv/bin/python scripts/provision.py explain
backend/.venv/bin/python scripts/provision.py dry-run
```

## Use production local LLM mode

Starter mode uses `dev` and selects the Qwen3 4B portable behavioral model. Production mode uses the host/policy-selected Qwen3 catalog model; the tiny Qwen2.5 model is retained only for explicit plumbing/startup diagnostics.

Preview the selected production model for the current host:

```bash
export LLM_MODEL_MODE=prod
backend/.venv/bin/python scripts/ensure_models.py --family llm --dry-run
```

Acquire or verify the selected production model and current-host llama.cpp runtime:

```bash
backend/.venv/bin/python scripts/ensure_models.py --family llm
backend/.venv/bin/python scripts/ensure_models.py --family llm --verify-only
```

Return the current shell to starter mode:

```bash
export LLM_MODEL_MODE=dev
```

Use `--all-llm` only when intentionally validating the full LLM catalog.

## Optional local services

Redis and SearXNG are provided by `docker-compose.yml`. The backend can run without them; dependent subsystems report unavailable or degraded when services are absent.

Normal text and voice turns can search the public web when the operator explicitly asks with phrasing such as `Search for ...`, `Research this ...`, or `Use research ...`. Search runs one query. Research may run up to three queries and read up to three public pages. The desktop shows progress, renders clickable sources, and exposes Stop while search work is active.

Enabled providers are attempted in this order: DDGS, SearXNG, then Tavily. The first provider that returns usable results completes that query. Configure provider access in `.env`:

```dotenv
USE_DDGS=true
USE_SEARXNG=true
USE_TAVILY=false
TAVILY_API_KEY=
```

`config/search/searxng/settings.yml` is the mounted SearXNG configuration authority and enables JSON responses. Private query details require confirmation before external disclosure; credentials and secrets are rejected.

> SearXNG defaults to host port `8080`, but that conflicts with `llama.cpp/llama-server`.
> SearXNG documents alternate port `8888`, but that conflicts with `unsloth/llama-server`.
> JARVISv7 sets SearXNG default to port `8910` in `docker-compose.yml` to avoid these conflicts.
> The SearXNG port is configurable in `.env:SEARXNG_PORT=****` if another port is required.

```bash
docker compose up --detach
docker compose down
```

## Backend and proving-host commands

The desktop preview starts the backend for normal use. Run the backend directly only for API development or diagnosis:

```bash
backend/.venv/bin/python scripts/run_backend.py
```

Default URL:

```text
http://127.0.0.1:8765
```

Useful options:

```bash
backend/.venv/bin/python scripts/run_backend.py --reload
backend/.venv/bin/python scripts/run_backend.py --host 127.0.0.1 --port 8765
```

Diagnostic text-only proving-host turn:

```bash
backend/.venv/bin/python scripts/run_jarvis.py --text-only --turns 1
```

Profile-only startup check:

```bash
backend/.venv/bin/python scripts/run_jarvis.py --profile
```

Voice-only proving-host turn requires working local STT, TTS, and an audio input device.

```bash
backend/.venv/bin/python scripts/run_jarvis.py --voice-only --turns 1
```

Voice proving requires working Linux audio input/output and compatible STT/TTS runtimes; neither is established by this broader Linux guide.

For WSLg transport inspection without claiming voice inference:

```bash
pactl info
pactl list short sources
pactl list short sinks
```

The proving host exposed `RDPSource` and `RDPSink`; the resident stream started without a reported audio error. This is transport/startup evidence only, not STT, TTS, wake-detection, or end-to-end voice evidence.

## Development validation

Quick checks (use these first):

```bash
backend/.venv/bin/python scripts/provision.py verify
backend/.venv/bin/python scripts/validate_backend.py profile
```

Deeper validation tiers (only needed for development work on the backend itself):

```bash
backend/.venv/bin/python scripts/validate_backend.py unit
backend/.venv/bin/python scripts/validate_backend.py integration
backend/.venv/bin/python scripts/validate_backend.py runtime
backend/.venv/bin/python scripts/validate_backend.py ci
npm --prefix desktop test
```

Live tests are gated behind hardware/service availability and are off by default:

```bash
export JARVISV7_LIVE_TESTS=1
```

Then run the focused live test you need.

```bash
backend/.venv/bin/python scripts/validate_backend.py runtime --families search
```

## Repository rules that matter

- `pyproject.toml` is the Python dependency source of truth.
- `backend/requirements.txt` is generated; do not edit it by hand.
- Use `scripts/provision.py` for Python dependency installation.
- Use `scripts/ensure_models.py` for configured model artifacts.
- Keep generated models, runtimes, caches, and reports out of source commits unless a slice explicitly says otherwise.
- Record validation claims with exact command evidence.
- Do not treat this guide as evidence for Linux paths beyond the verified Linux AMD64 NVIDIA CUDA llama.cpp route.

## Common fixes

Python version rejected:

```text
Install Python 3.11, 3.12, or 3.13 with venv support, then recreate backend/.venv.
```

Provisioning failed:

```bash
backend/.venv/bin/python scripts/provision.py explain
backend/.venv/bin/python scripts/provision.py install
```

Models missing:

```bash
backend/.venv/bin/python scripts/ensure_models.py
```

Backend starts but reports degraded readiness:

```bash
backend/.venv/bin/python scripts/validate_backend.py profile
```

Desktop shell fails before app launch:

```bash
npm --prefix desktop install
npm --prefix desktop test
```

## Appendix 1: Cross-distribution desktop graphics and audio

This appendix maps the native packages and session services commonly required to display the existing Tauri 2 shell and expose microphone/speaker devices. Package names vary by distribution, and these mappings are guidance rather than JARVIS validation evidence.

### Graphics and tray prerequisites

The desktop shell requires GTK 3, WebKitGTK 4.1, OpenSSL, librsvg, a C/C++ toolchain, `pkg-config`, and an AppIndicator implementation for the tray boundary. It also needs an active Wayland or X11 graphical session.

| Distribution family | Typical package mapping |
|---|---|
| Debian / Ubuntu | `build-essential`, `pkg-config`, `libgtk-3-dev`, `libwebkit2gtk-4.1-dev`, `libssl-dev`, `librsvg2-dev`, `libayatana-appindicator3-dev` |
| Fedora / RHEL | Development Tools, `pkgconf-pkg-config`, `gtk3-devel`, `webkit2gtk4.1-devel`, `openssl-devel`, `librsvg2-devel`, and the available Ayatana/AppIndicator development package |
| Arch / Manjaro | `base-devel`, `pkgconf`, `gtk3`, `webkit2gtk-4.1`, `openssl`, `librsvg`, `libayatana-appindicator` |
| openSUSE | C/C++ development pattern, `pkg-config`, GTK 3, WebKitGTK 4.1, OpenSSL, librsvg, and AppIndicator/Ayatana `-devel` packages |
| Alpine | `build-base`, `pkgconf`, and the equivalent GTK, WebKitGTK 4.1, OpenSSL, librsvg, and AppIndicator `-dev` packages; musl-based builds require separate validation |
| NixOS | Supply GTK, WebKitGTK, OpenSSL, librsvg, AppIndicator, Rust, Node.js, and native build tools through the project development shell rather than assuming system-wide packages |

A minimal or headless installation does not become a supported desktop host merely because the libraries compile. It still needs a user graphical session and working compositor/display server.

Check the active display transport before launch:

```bash
printf 'DISPLAY=%s\nWAYLAND_DISPLAY=%s\nXDG_SESSION_TYPE=%s\n' \
  "$DISPLAY" "$WAYLAND_DISPLAY" "$XDG_SESSION_TYPE"
```

### Audio services and devices

JARVIS audio ultimately depends on ALSA devices exposed through a working user audio service. Most current desktop distributions use PipeWire with WirePlumber and the `pipewire-pulse` compatibility service; older installations may use PulseAudio directly. `pactl` can work in either case because PipeWire provides a PulseAudio-compatible server.

Typical host requirements are:

- ALSA runtime and development libraries needed by native/Python audio dependencies;
- PipeWire plus WirePlumber and `pipewire-pulse`, or a working PulseAudio user service;
- PulseAudio client tools for diagnostics such as `pactl`;
- a default input source and output sink;
- user-session permission to access the microphone and speakers.

Inspect the active audio path with:

```bash
pactl info
pactl list short sources
pactl list short sinks
systemctl --user --no-pager status pipewire pipewire-pulse wireplumber
```

The `systemctl` command may report missing units on a PulseAudio-only system; in that case, confirm the PulseAudio user service instead. Successful transport checks establish device visibility only. They do not prove STT, TTS, wake detection, echo handling, or an end-to-end voice turn.

### Cross-distribution validation boundary

Each distribution family remains a separate proving target because package availability, WebKitGTK versions, tray behavior, sandboxing, and user audio defaults differ. Keep capability identifiers normalized by operating system, architecture, and device; do not introduce distribution-specific runtime identifiers solely for setup differences.

## Appendix 2: WSL2 host setup

This appendix records setup used for Ubuntu 22.04 under WSL2, the proving environment for the verified Linux AMD64 NVIDIA CUDA llama.cpp route. It does not establish a complete Linux desktop or voice runtime path.

### Preserve Ubuntu's system Python

Do not remove Ubuntu 22.04's Python 3.10, replace `/usr/bin/python3`, or configure `update-alternatives` for it. Ubuntu owns that interpreter, and replacing it can break `apt` and other system utilities.

Install Python 3.12.10 side-by-side under `/usr/local` with `make altinstall`. Repository dependencies must still live only in `backend/.venv`, never in the global interpreter.

### Sudo when working through Codex

Codex command approval permits execution outside the workspace sandbox, but it does not grant root access or provide a safe place to submit a sudo password. Never send a sudo password through chat. Run the privileged commands below directly in a WSL terminal, then return to Codex for verification and repo-local work.

### Install build prerequisites

Run each command separately:

```bash
sudo apt-get update
```

```bash
sudo apt-get install --yes build-essential pkg-config curl ca-certificates xz-utils libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev libncursesw5-dev tk-dev uuid-dev libasound2-plugins
```

For WSLg audio, `libasound2-plugins` enables PortAudio's PulseAudio device. Without it, JARVIS may see only the invalid default device `-1`.

### Install Tauri desktop prerequisites

The existing Tauri 2 shell uses GTK/WebKitGTK for its window and Ayatana AppIndicator for its tray boundary:

```bash
sudo apt-get install --yes build-essential pkg-config curl wget file libssl-dev libgtk-3-dev libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev
```

Verify the WSLg display and audio bridges before launching:

```bash
printf 'DISPLAY=%s\nWAYLAND_DISPLAY=%s\nPULSE_SERVER=%s\n' "$DISPLAY" "$WAYLAND_DISPLAY" "$PULSE_SERVER"
pactl info
```

### Build and install Python 3.12.10

Download the exact official source release:

```bash
cd /tmp
curl --fail --location --remote-name https://www.python.org/ftp/python/3.12.10/Python-3.12.10.tar.xz
tar --extract --file Python-3.12.10.tar.xz
cd Python-3.12.10
```

Configure and build it. `--enable-optimizations` makes the build slower but enables Python's profile-guided optimizations.

```bash
./configure --prefix=/usr/local --with-ensurepip=install --enable-optimizations
make -j"$(nproc)"
```

Install it without replacing the system `python3` command:

```bash
sudo make altinstall
```

Verify the global side-by-side interpreter and its bundled pip:

```bash
/usr/local/bin/python3.12 --version
/usr/local/bin/python3.12 -m pip --version
```

The expected interpreter version is `Python 3.12.10`.

### Create and verify the repo environment

From the repository root:

```bash
/usr/local/bin/python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python --version
backend/.venv/bin/python -m pip --version
```

At this point the environment should be isolated and usable, but repository dependencies are not installed until the approved provisioning flow is run. A fresh venv containing only pip is expected to fail `scripts/provision.py verify` by reporting the required packages as missing.
