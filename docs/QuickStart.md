# Quick Start

This guide sets up and launches the repo-run JARVISv7 desktop preview on Windows using repo-owned commands.

Run commands from PowerShell at the repository root. Do not install Python packages globally for this repo.

## Prerequisites

Backend setup:

- Windows PowerShell
- Git
- Python `>=3.11,<3.14` through the Windows `py` launcher
- Internet access for dependency and model acquisition

Desktop shell:

- Node.js and npm
- Rust toolchain
- Tauri Windows prerequisites

Optional local services:

- Docker Desktop for Redis and SearXNG

## Clone

```powershell
git clone https://github.com/bentman/JARVISv7.git
Set-Location .\JARVISv7
```

For an existing clone:

```powershell
Set-Location <REPO_ROOT_PATH>
git pull
```

## Before you touch config or dependencies

Three rules prevent the most common self-inflicted setup problems:

- **`pyproject.toml` is the only place Python dependencies are declared.** `backend\requirements.txt` is *generated* from it by `scripts\provision.py lock` (base extra only) and is read by tooling, not by you. Never hand-edit it — regenerate it instead if it's ever out of sync.
- **`.env` overrides `.env.example` key-by-key, not wholesale.** Both files are loaded; `.env` values win only for the keys it actually sets. Leaving a key out of `.env` means the `.env.example` (or hardcoded) default still applies. Never edit `.env.example` for local changes — copy it to `.env` first.
- **Not all settings are meant to be touched.** `backend\app\core\settings.py` classifies every setting as `primary`, `advanced`, `derived`, `services`, `secret`, `compatibility`, or `test-only`. Stick to `primary` settings (see below) unless you have a specific reason to go further:

  | Class | Meaning | Examples |
  |---|---|---|
  | `primary` | Safe, expected day-to-day toggles | `USE_LOCAL_MODEL`, `LLM_MODEL_MODE`, `USE_OLLAMA`, `USE_SEARXNG` |
  | `advanced` | Path/tuning overrides, rarely needed | `MODEL_PATH`, `LLAMA_CPP_TIMEOUT_SECONDS` |
  | `derived` | Computed from a `primary` setting unless explicitly set | `LOCAL_MODEL_FETCH`, `LLAMA_CPP_MANAGED` |
  | `services` | Only matters if the optional Docker service is running | `REDIS_PORT`, `SEARXNG_PORT` |
  | `secret` | Credentials | `PICOVOICE_ACCESS_KEY`, `TAVILY_API_KEY` |
  | `compatibility` / `test-only` | Legacy or CI-only | `JARVISV7_OLLAMA_URL`, `JARVISV7_LIVE_TESTS` |

## Repo-run desktop preview

Use this path for the normal product-preview flow:

```text
prepare shell -> create backend venv -> bootstrap -> install desktop deps -> launch desktop
```

The desktop shell starts the backend, creates or resumes a session, loads readiness, starts the resident voice stream when available, and displays backend, readiness, service, wake, resident voice, and session state.

### 1. Prepare PowerShell

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:TEMP = "$PWD\cache\temp"
$env:TMP = "$PWD\cache\temp"
$env:TMPDIR = "$PWD\cache\temp"
$env:PIP_CACHE_DIR = "$PWD\cache\pip"
New-Item -ItemType Directory -Force $env:TEMP, $env:PIP_CACHE_DIR | Out-Null
```

### 2. Create the backend environment

Prefer Python 3.13 when available:

```powershell
py -3.13 -m venv backend\.venv
.\backend\.venv\Scripts\python -m pip install --upgrade pip
```

Fallback if needed:

```powershell
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\python -m pip install --upgrade pip
```

### 3. Use starter settings

For first setup, leave `.env.example` defaults in place and just copy it:

```powershell
Copy-Item .env.example .env
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

### 4. Bootstrap backend dependencies and models

```powershell
.\backend\.venv\Scripts\python scripts\bootstrap.py
```

Bootstrap runs 5 checkpoints in order and stops at the first failure — fix that checkpoint, don't work around it manually:

| # | Checkpoint | What it does |
|---|---|---|
| 1 | `profile` | Detects host hardware (CPU/GPU/NPU, arch) |
| 2 | `provision` | Runs `scripts\provision.py install` — resolves hardware-appropriate extras from `pyproject.toml` and installs them |
| 3 | `ensure_models` | Runs `scripts\ensure_models.py` — acquires/verifies STT, TTS, wake, and LLM model artifacts (see below) |
| 4 | `preflight` | Probes STT/TTS/LLM/wake readiness and reports token/probe status |
| 5 | `validate_profile` | Runs `scripts\validate_backend.py profile` as a final sanity check |

If it fails, the checkpoint name and reason printed tells you which of the four commands above to run standalone for a fuller error.

### 5. Install desktop dependencies and launch

```powershell
npm --prefix desktop install
npm --prefix desktop test
npm --prefix desktop run dev
```

Do not install Tauri globally for this repo. Use repo-local desktop package commands.

The running desktop is the main product-preview surface. Use its readiness, services, resident voice, wake, session, and error panels before dropping to backend scripts.

## Model acquisition

`scripts\ensure_models.py` manages four independent model families: `stt`, `tts`, `wake`, `llm`. Bootstrap acquires all of them; you only need this section if one family fails or you want to manage it directly.

```powershell
.\backend\.venv\Scripts\python scripts\ensure_models.py --family llm --verify-only
.\backend\.venv\Scripts\python scripts\ensure_models.py --family stt --verify-only
.\backend\.venv\Scripts\python scripts\ensure_models.py --family tts --verify-only
.\backend\.venv\Scripts\python scripts\ensure_models.py --family wake --verify-only
```

Drop `--verify-only` to acquire a missing/mismatched artifact for that family.

Some catalog entries are not plain downloads — the catalog can mark an entry `pending-pinned-release`, `pending-viability`, or `build-required`. If a family fails to resolve and the error references one of these, that model needs manual build/export steps rather than a retry (see **Hardware acceleration** below for the ARM64/NPU case).

## Hardware acceleration (ARM64 / QNN NPU / OpenCL GPU)

Provisioning and model selection are hardware-aware by default — `scripts\provision.py` and `scripts\ensure_models.py` pick appropriate extras and runtimes for the detected host automatically. **Most hosts need nothing further.**

If you're on **Windows ARM64 (Snapdragon)** and want NPU (QNN) or GPU (Adreno OpenCL) acceleration rather than CPU fallback, you need one of the accelerator workaround docs — these are two-host workflows (an AMD64 host prepares/exports an artifact, the ARM64 host stages and runs it) because the export tooling (`qai_hub_models`) requires x64 Python and cannot run inside the ARM64 repo venv:

```text
docs\jarvis-arm-llamacpp.md   — Adreno OpenCL llama.cpp sidecar
docs\jarvis-arm-whisper.md    — Qualcomm QNN Whisper STT artifact
```

Skip these entirely on x64 hosts or if CPU-only local inference is acceptable.

Useful checks on any host:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py explain
.\backend\.venv\Scripts\python scripts\provision.py dry-run
```

## Use production local LLM mode

Starter mode uses `dev` and selects `assistant-small-q4`. Production mode uses the host/policy-selected Qwen3 catalog model.

Preview the selected production model for the current host:

```powershell
$env:LLM_MODEL_MODE = "prod"
.\backend\.venv\Scripts\python scripts\ensure_models.py --family llm --dry-run
```

Acquire or verify the selected production model and current-host llama.cpp runtime:

```powershell
$env:LLM_MODEL_MODE = "prod"
.\backend\.venv\Scripts\python scripts\ensure_models.py --family llm
.\backend\.venv\Scripts\python scripts\ensure_models.py --family llm --verify-only
```

Return the current shell to starter mode:

```powershell
$env:LLM_MODEL_MODE = "dev"
```

Use `--all-llm` only when intentionally validating the full LLM catalog.

## Optional local services

Redis and SearXNG are provided by `docker-compose.yml`. The backend can run without them; dependent subsystems report unavailable or degraded when services are absent.

SearXNG defaults to host port `8888`.

```powershell
docker compose up --detach
docker compose down
```

## Backend and proving-host commands

The desktop preview starts the backend for normal use. Run the backend directly only for API development or diagnosis:

```powershell
.\backend\.venv\Scripts\python scripts\run_backend.py
```

Default URL:

```text
http://127.0.0.1:8765
```

Useful options:

```powershell
.\backend\.venv\Scripts\python scripts\run_backend.py --reload
.\backend\.venv\Scripts\python scripts\run_backend.py --host 127.0.0.1 --port 8765
```

Diagnostic text-only proving-host turn:

```powershell
.\backend\.venv\Scripts\python scripts\run_jarvis.py --text-only --turns 1
```

Profile-only startup check:

```powershell
.\backend\.venv\Scripts\python scripts\run_jarvis.py --profile
```

Voice-only proving-host turn requires working local STT, TTS, and an audio input device.

```powershell
.\backend\.venv\Scripts\python scripts\run_jarvis.py --voice-only --turns 1
```

## Development validation

Quick checks (use these first):

```powershell
.\backend\.venv\Scripts\python scripts\provision.py verify
.\backend\.venv\Scripts\python scripts\validate_backend.py profile
```

Deeper validation tiers (only needed for development work on the backend itself):

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py unit
.\backend\.venv\Scripts\python scripts\validate_backend.py integration
.\backend\.venv\Scripts\python scripts\validate_backend.py runtime
.\backend\.venv\Scripts\python scripts\validate_backend.py ci
npm --prefix desktop test
```

Live tests are gated behind hardware/service availability and are off by default:

```powershell
$env:JARVISV7_LIVE_TESTS = "1"
```

Then run the focused live test you need.

## Repository rules that matter

- `pyproject.toml` is the Python dependency source of truth.
- `backend\requirements.txt` is generated; do not edit it by hand.
- Use `scripts\provision.py` for Python dependency installation.
- Use `scripts\ensure_models.py` for configured model artifacts.
- Keep generated models, runtimes, caches, and reports out of source commits unless a slice explicitly says otherwise.
- Record validation claims with exact command evidence.

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