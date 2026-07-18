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
See [Appendix: WSL2 host setup](#appendix-wsl2-host-setup) before creating the repo environment.

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

- **`pyproject.toml` is the only place Python dependencies are declared.** `backend/requirements.txt` is generated from it by `scripts/provision.py lock` for the base extra only. Never hand-edit it.
- **`.env` overrides `.env.example` key-by-key.** Never edit `.env.example` for local changes; copy it to `.env` first.
- **Not all settings are operator settings.** Prefer settings classified as `primary` in `backend/app/core/settings.py` unless a specific task requires another class.

| Class | Meaning | Examples |
|---|---|---|
| `primary` | Safe, expected day-to-day toggles | `USE_LOCAL_MODEL`, `LLM_MODEL_MODE`, `USE_OLLAMA`, `USE_SEARXNG` |
| `advanced` | Path/tuning overrides, rarely needed | `MODEL_PATH`, `LLAMA_CPP_TIMEOUT_SECONDS` |
| `derived` | Computed from a primary setting unless explicitly set | `LOCAL_MODEL_FETCH`, `LLAMA_CPP_MANAGED` |
| `services` | Relevant when the optional service is running | `REDIS_PORT`, `SEARXNG_PORT` |
| `secret` | Credentials | `PICOVOICE_ACCESS_KEY`, `TAVILY_API_KEY` |
| `compatibility` / `test-only` | Legacy or CI-only | `JARVISV7_OLLAMA_URL`, `JARVISV7_LIVE_TESTS` |

## Repo-run desktop preview

The intended flow is:

```text
prepare shell -> create backend venv -> bootstrap -> install desktop deps -> launch desktop
```

The desktop shell should start the backend, create or resume a session, load readiness, start resident voice when available, and display backend, service, wake, voice, session, and error state.

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
python3.13 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
```

Fallback if needed:

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
```

> Use `backend/.venv/bin/python` for the validated Linux AMD64 CUDA path.

### 3. Use starter settings

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

Keep `LLM_MODEL_ID` blank unless you intentionally want an explicit model override.

### 4. Bootstrap backend dependencies and models

```bash
backend/.venv/bin/python scripts/bootstrap.py
```

Bootstrap is intended to run these checkpoints in order:

| # | Checkpoint | Purpose |
|---|---|---|
| 1 | `profile` | Detect host CPU, GPU, NPU, and architecture |
| 2 | `provision` | Resolve and install hardware-appropriate extras from `pyproject.toml` |
| 3 | `ensure_models` | Acquire or verify STT, TTS, wake, and LLM artifacts |
| 4 | `preflight` | Probe runtime readiness |
| 5 | `validate_profile` | Run the backend profile validator |

Stop at the first failure and diagnose that checkpoint. Do not work around provisioning with global or ad hoc package installation.

Wake support remains evidence-dependent. On the current WSL2 proving host, OpenWakeWord imported, reported ready, and its monitor ran over the resident stream. That establishes startup and monitoring only; it does not validate wake detection or a completed voice turn on Linux.

### 5. Install desktop dependencies and launch

```bash
npm --prefix desktop install
npm --prefix desktop test
npm --prefix desktop run dev
```

Do not install Tauri globally. On the current WSL2/WSLg proving host, the shell built and launched, started the backend through `backend/.venv/bin/python scripts/run_backend.py`, created a session, loaded readiness, and polled the consolidated desktop status API. Audio inference and completed resident voice turns remain unvalidated.

For a compile-only proof before opening a window:

```bash
cargo check --manifest-path desktop/src-tauri/Cargo.toml
npm --prefix desktop run build
```

The WSLg proof emitted two non-fatal GTK scale-factor diagnostics during startup. They did not terminate the shell or prevent the frontend/backend lifecycle. Tray construction completed, but WSLg tray presentation was not separately confirmed.

## Model acquisition

Bootstrap is intended to manage the `stt`, `tts`, `wake`, and `llm` model families. For focused verification:

```bash
backend/.venv/bin/python scripts/ensure_models.py --family llm --verify-only
backend/.venv/bin/python scripts/ensure_models.py --family stt --verify-only
backend/.venv/bin/python scripts/ensure_models.py --family tts --verify-only
backend/.venv/bin/python scripts/ensure_models.py --family wake --verify-only
```

Drop `--verify-only` to request acquisition of a missing or mismatched artifact. Catalog entries marked `pending-pinned-release`, `pending-viability`, or `build-required` require additional work rather than repeated downloads.

## Hardware acceleration

Linux AMD64 NVIDIA CUDA is verified for the managed llama.cpp sidecar: b9704 / commit `10786217e9d40c848ac0133cbe9c5f22a52421bb` / build 9704, using `/usr/local/cuda-12.4` and `runtimes/llama.cpp/linux-amd64-cuda`. The live proof starts the managed sidecar, exercises health/models/completion, confirms CUDA offload, and leaves no `llama-server` process. See [Linux llama.cpp CUDA build](jarvis-wsl-llamacpp.md).

ROCm, Vulkan, OpenCL, other Linux accelerator paths, and Linux desktop/audio behavior remain outside this verified claim.

Useful intended diagnostics:

```bash
backend/.venv/bin/python scripts/provision.py explain
backend/.venv/bin/python scripts/provision.py dry-run
```

## Use production local LLM mode

Starter mode selects the development model. To preview production selection in the current shell:

```bash
export LLM_MODEL_MODE=prod
backend/.venv/bin/python scripts/ensure_models.py --family llm --dry-run
```

Acquire or verify the selected model and runtime:

```bash
backend/.venv/bin/python scripts/ensure_models.py --family llm
backend/.venv/bin/python scripts/ensure_models.py --family llm --verify-only
```

Return to starter mode:

```bash
export LLM_MODEL_MODE=dev
```

Use `--all-llm` only when intentionally validating the full LLM catalog.

## Optional local services

Redis and SearXNG are declared in `docker-compose.yml`; the backend should degrade visibly when they are absent.

```bash
docker compose up --detach
docker compose down
```

SearXNG defaults to host port `8888`.

## Backend and proving-host commands

Run the backend directly only for API development or diagnosis:

```bash
backend/.venv/bin/python scripts/run_backend.py
```

Default URL: `http://127.0.0.1:8765`

```bash
backend/.venv/bin/python scripts/run_backend.py --reload
backend/.venv/bin/python scripts/run_backend.py --host 127.0.0.1 --port 8765
backend/.venv/bin/python scripts/run_jarvis.py --text-only --turns 1
backend/.venv/bin/python scripts/run_jarvis.py --profile
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

Quick intended checks:

```bash
backend/.venv/bin/python scripts/provision.py verify
backend/.venv/bin/python scripts/validate_backend.py profile
```

Deeper tiers:

```bash
backend/.venv/bin/python scripts/validate_backend.py unit
backend/.venv/bin/python scripts/validate_backend.py integration
backend/.venv/bin/python scripts/validate_backend.py runtime
backend/.venv/bin/python scripts/validate_backend.py ci
npm --prefix desktop test
```

Live tests remain gated behind hardware and service availability:

```bash
export JARVISV7_LIVE_TESTS=1
```

## Repository rules that matter

- `pyproject.toml` is the Python dependency source of truth.
- `backend/requirements.txt` is generated; do not edit it manually.
- Use repository provisioning and model-management scripts rather than ad hoc installs.
- Keep generated models, runtimes, caches, and reports out of source commits unless explicitly required.
- Record validation claims with exact command evidence.
- Do not treat this guide as evidence for Linux paths beyond the verified Linux AMD64 NVIDIA CUDA llama.cpp route.

## Common diagnostic starting points

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

Backend reports degraded readiness:

```bash
backend/.venv/bin/python scripts/validate_backend.py profile
```

Desktop fails before launch:

```bash
npm --prefix desktop install
npm --prefix desktop test
```

## Appendix: WSL2 host setup

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
