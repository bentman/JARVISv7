# Quick Start

This guide sets up and launches the current repo-run JARVISv7 desktop preview on Windows using repo-owned commands.

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

## Shortest supported desktop path

Use this path for first setup and normal product-preview launch:

```text
prepare shell -> create backend venv -> copy starter settings -> bootstrap -> install desktop deps -> launch desktop
```

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:TEMP = "$PWD\cache\temp"
$env:TMP = "$PWD\cache\temp"
$env:TMPDIR = "$PWD\cache\temp"
$env:PIP_CACHE_DIR = "$PWD\cache\pip"
New-Item -ItemType Directory -Force $env:TEMP, $env:PIP_CACHE_DIR | Out-Null

py -3.13 -m venv backend\.venv
.\backend\.venv\Scripts\python -m pip install --upgrade pip

Copy-Item .env.example .env

.\backend\.venv\Scripts\python scripts\bootstrap.py

npm --prefix desktop install
npm --prefix desktop run dev
```

Fallback if Python 3.13 is unavailable:

```powershell
py -3.12 -m venv backend\.venv
.\backend\.venv\Scripts\python -m pip install --upgrade pip
```

Do not install Tauri globally for this repo. Use repo-local desktop package commands.

The running desktop is the main product-preview surface. The desktop shell starts the backend, creates or resumes a session, loads readiness, starts the resident voice stream when available, and displays backend, readiness, service, wake, resident voice, session, error, and backend diagnostics state.

## Starter settings

JARVIS loads `.env` when present. If `.env` is missing, it falls back to `.env.example`.

For first setup, copy `.env.example` to `.env` and keep the starter defaults unless you are intentionally changing runtime policy:

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

## After the desktop opens

Check the desktop surface before dropping to backend scripts:

1. Backend / Health
2. Readiness
3. Services
4. Backend diagnostics
5. Conversation debug details
6. Degraded list detail, only when visible

Backend startup failures should show the Python path, backend script path, working directory, endpoint, log paths, and useful log tail output in the Backend diagnostics detail panel.

## Troubleshooting and focused checks

Use these commands when bootstrap or desktop launch fails, or when the desktop reports degraded readiness.

Verify installed Python requirements:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py verify
```

Verify selected model artifacts:

```powershell
.\backend\.venv\Scripts\python scripts\ensure_models.py --family llm --verify-only
```

Inspect backend profile and readiness evidence:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py profile
```

For a broader backend check:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py regression
```

For the desktop static contract:

```powershell
npm --prefix desktop test
```

## Optional local services

Redis and SearXNG are provided by `docker-compose.yml`. The backend can run without them; dependent subsystems report unavailable or degraded when services are absent.

SearXNG defaults to host port `8888`.

```powershell
docker compose up --detach
docker compose down
```

## Production local LLM mode

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

## Developer and diagnostic commands

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

## Settings and advanced overrides

Most first-run users should only use `.env` copied from `.env.example`.

Advanced environment variables are defined and classified in `backend\app\core\settings.py`. That module loads `.env` first, falls back to `.env.example` when `.env` is missing, and maps environment variables into the backend `Settings` object.

Use `backend\app\core\settings.py` as the source of truth for advanced override names and their categories:

- primary settings: normal user-facing runtime policy such as `USE_LOCAL_MODEL`, `LLM_MODEL_MODE`, `LLM_MODEL_POLICY`, `USE_OLLAMA`, `OLLAMA_MODEL`, `USE_SEARXNG`, `USE_DDGS`, and `USE_TAVILY`;
- advanced settings: paths, llama.cpp endpoint and artifact overrides, voice timing thresholds, and model directories;
- services settings: Redis and SearXNG host/port values;
- secret settings: API keys and access keys;
- test-only settings: live-test gates.

Do not add new `.env` keys unless code reads them through `backend\app\core\settings.py` or an adjacent settings path.

## Development validation

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py unit
.\backend\.venv\Scripts\python scripts\validate_backend.py integration
.\backend\.venv\Scripts\python scripts\validate_backend.py runtime
.\backend\.venv\Scripts\python scripts\validate_backend.py ci
npm --prefix desktop test
```

Live tests are gated. Enable them only when the required hardware or external service is available.

```powershell
$env:JARVISV7_LIVE_TESTS = "1"
```

Then run the focused live test you need.

## Hardware and model notes

Provisioning is hardware-aware. The setup path detects the current host and selects the appropriate Python extras and local runtime profile.

Useful checks:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py explain
.\backend\.venv\Scripts\python scripts\provision.py dry-run
.\backend\.venv\Scripts\python scripts\ensure_models.py --family llm --verify-only
```

Optional native/runtime paths have separate helper docs:

```text
docs\jarvis-arm-llamacpp.md
docs\jarvis-arm-whisper.md
```

Use those only when working on Windows ARM64 Adreno OpenCL llama.cpp sidecar or Windows ARM64 Qualcomm QNN Whisper artifact paths.

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
