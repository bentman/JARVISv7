# Quick Start

This guide sets up a fresh JARVISv7 clone using the repository-owned setup and validation commands.

Run commands from PowerShell at the repository root unless a step says otherwise.

## What this setup does

The standard setup path:

- creates a repo-local Python virtual environment under `backend\.venv`
- installs Python packages through `scripts\provision.py`
- acquires or verifies configured model artifacts through `scripts\ensure_models.py`
- runs hardware-aware preflight checks
- validates the backend profile

Do not install Python packages globally for this repo.

## Prerequisites

Required for backend setup:

- Windows PowerShell
- Git
- Python `>=3.11,<3.14` available through the Windows `py` launcher
- Internet access for package/model acquisition

Required for the desktop shell:

- Node.js and npm
- Rust toolchain
- Tauri Windows prerequisites

Optional:

- Docker Desktop for Redis and SearXNG local services
- Visual Studio/CMake/native tools only for native runtime sidecar work

## Clone and enter the repo

```powershell
git clone https://github.com/bentman/JARVISv7.git
Set-Location .\JARVISv7
```

For an existing clone:

```powershell
Set-Location <REPO_ROOT_PATH>
```

## Prepare the shell

Use UTF-8 output and repo-local cache/temp folders during setup.

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:TEMP = "$PWD\cache\temp"
$env:TMP = "$PWD\cache\temp"
$env:TMPDIR = "$PWD\cache\temp"
$env:PIP_CACHE_DIR = "$PWD\cache\pip"
New-Item -ItemType Directory -Force $env:TEMP, $env:PIP_CACHE_DIR | Out-Null
```

## Create the Python environment

Prefer Python 3.13 when available.

```powershell
py -3.13 -m venv backend\.venv
```

Fallback to another supported installed version if needed.

```powershell
py -3.12 -m venv backend\.venv
```

Upgrade pip inside the repo virtual environment.

```powershell
.\backend\.venv\Scripts\python -m pip install --upgrade pip
```

## Run bootstrap

```powershell
.\backend\.venv\Scripts\python scripts\bootstrap.py
```

Bootstrap runs the repository setup checkpoints in order. If it fails, stop at the failed checkpoint and fix that prerequisite. Do not work around it by manually installing random packages.

## Verify setup

Run these after bootstrap.

```powershell
.\backend\.venv\Scripts\python scripts\provision.py verify
.\backend\.venv\Scripts\python scripts\ensure_models.py --verify-only
.\backend\.venv\Scripts\python scripts\validate_backend.py profile
```

For a broader backend check:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py regression
```

## Configure local settings

JARVIS loads `.env` when present. If `.env` is missing, it falls back to `.env.example`.

Create `.env` only when you need local overrides.

```powershell
Copy-Item .env.example .env
```

Common local settings:

```text
USE_LOCAL_MODEL=false
LOCAL_MODEL_FETCH=false
LLAMA_CPP_MANAGED=false
USE_OLLAMA=true
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=phi4-mini
```

Leave defaults alone for first setup unless you already know which runtime path you are validating.

## Optional local services

Redis and SearXNG are provided by `docker-compose.yml`. The backend can run without them; dependent subsystems report unavailable or degraded when services are absent.

Start services:

```powershell
docker compose up --detach
```

Stop services:

```powershell
docker compose down
```

## Run the backend API

```powershell
.\backend\.venv\Scripts\python scripts\run_backend.py
```

Default bind:

```text
http://127.0.0.1:8765
```

Useful options:

```powershell
.\backend\.venv\Scripts\python scripts\run_backend.py --reload
.\backend\.venv\Scripts\python scripts\run_backend.py --host 127.0.0.1 --port 8765
```

## Run a diagnostic turn

Text-only proving-host turn:

```powershell
.\backend\.venv\Scripts\python scripts\run_jarvis.py --text-only --turns 1
```

Profile-only startup check:

```powershell
.\backend\.venv\Scripts\python scripts\run_jarvis.py --profile
```

Voice-only turn requires working local STT, TTS, and an audio input device.

```powershell
.\backend\.venv\Scripts\python scripts\run_jarvis.py --voice-only --turns 1
```

## Run the desktop shell

Install repo-local desktop dependencies.

```powershell
npm --prefix desktop install
```

Run the Tauri desktop shell.

```powershell
npm --prefix desktop run dev
```

Do not install Tauri globally for this repo. Use the repo-local desktop package commands.

## Development validation

Unit tests:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py unit
```

Integration tests:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py integration
```

Runtime tests, excluding live hardware unless explicitly enabled:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py runtime
```

CI-safe validation:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py ci
```

Desktop static test:

```powershell
npm --prefix desktop test
```

## Live tests

Live tests are gated. Enable them only when the required hardware or external service is present.

```powershell
$env:JARVISV7_LIVE_TESTS = "1"
```

Then run the focused live test you need. Do not use live-test results as general validation unless the required hardware path was actually available.

## Hardware and model notes

Provisioning is hardware-aware. The setup path detects the current host and selects the appropriate Python extras.

Useful hardware/model checks:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py explain
.\backend\.venv\Scripts\python scripts\provision.py dry-run
.\backend\.venv\Scripts\python scripts\ensure_models.py --family llm --model assistant-small-q4 --verify-only
```

Optional native/runtime paths have their own helper docs:

```text
docs\jarvis-arm-llamacpp.md
docs\jarvis-arm-whisper.md
```

Use those only when working on the Windows ARM64 Adreno OpenCL llama.cpp sidecar or Windows ARM64 Qualcomm QNN Whisper artifact path.

## Repository rules that matter

- `pyproject.toml` is the Python dependency source of truth.
- `backend\requirements.txt` is generated; do not edit it by hand.
- Use `scripts\provision.py` for Python dependency installation.
- Use `scripts\ensure_models.py` for configured model artifacts.
- Keep generated models, runtimes, caches, and reports out of source commits unless a slice explicitly says otherwise.
- Record validation claims with the exact command evidence.

## Common fixes

Python version rejected:

```text
Install Python 3.11, 3.12, or 3.13 and recreate backend\.venv.
```

Provisioning failed:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py explain
.\backend\.venv\Scripts\python scripts\provision.py install
```

Models missing:

```powershell
.\backend\.venv\Scripts\python scripts\ensure_models.py
```

Backend starts but reports degraded readiness:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py profile
```

Desktop shell fails before app launch:

```powershell
npm --prefix desktop install
npm --prefix desktop test
```
