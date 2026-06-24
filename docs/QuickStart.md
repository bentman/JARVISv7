# Quick Start

## Purpose

Set up a fresh JARVISv7 clone for local use or development using the repository-owned setup paths.

This guide is intentionally short. When a command here fails, stop at that command and fix the reported prerequisite before continuing.

## Prerequisites

- Windows PowerShell from the repository root.
- Git (to clone repo `git clone https://github.com/bentman/JARVISv7.git`)
- Python `>=3.11` available through the Windows `py` launcher.
- Node.js and npm for the desktop shell.
- Rust and the Tauri system prerequisites for `npm --prefix desktop run dev`.
- Docker Desktop if you want the optional Redis and SearXNG local service substrate.

Do not install Python packages globally for this repository. All PowerShell commands below use `.\backend\.venv\Scripts\python`.

## Fresh Clone Setup

Run from the repository root:

```powershell
Set-Location <REPO_ROOT_PATH>
```

Use UTF-8 output and repo-local temporary/cache paths for setup commands:

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:TEMP = "$PWD\cache\temp"
$env:TMP = "$PWD\cache\temp"
$env:TMPDIR = "$PWD\cache\temp"
$env:PIP_CACHE_DIR = "$PWD\cache\pip"
New-Item -ItemType Directory -Force $env:TEMP, $env:PIP_CACHE_DIR | Out-Null
```

Create the local Python environment:

```powershell
py -3.13 -m venv backend\.venv
```

If Python 3.13 is not installed, use another supported installed version:

```powershell
py -3.12 -m venv backend\.venv
```

Upgrade pip inside the repository virtual environment:

```powershell
.\backend\.venv\Scripts\python -m pip install --upgrade pip
```

Run the repository bootstrap:

```powershell
.\backend\.venv\Scripts\python scripts\bootstrap.py
```

`scripts\bootstrap.py` runs the required setup checkpoints in order:

- hardware profile
- hardware-aware Python provisioning through `scripts\provision.py`
- model acquisition or verification through `scripts\ensure_models.py`
- preflight readiness
- backend profile validation

If bootstrap fails, do not install missing packages by hand. Fix the failed prerequisite or rerun the repository-owned command that failed.

## Verify Setup

Verify Python provisioning:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py verify
```

Verify model artifacts:

```powershell
.\backend\.venv\Scripts\python scripts\ensure_models.py --verify-only
```

Verify host profile and readiness:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py profile
```

For a broader backend check:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py regression
```

## Optional Local Services

Redis and SearXNG are provided by `docker-compose.yml`. They are optional runtime substrate services; the backend should report unavailable or degraded states when a dependent subsystem cannot use them.

Start them from the repository root:

```powershell
docker compose up --detach
```

Stop them when finished:

```powershell
docker compose down
```

## Run the Backend API

Start the backend API only:

```powershell
.\backend\.venv\Scripts\python scripts\run_backend.py
```

Default API bind:

```text
http://127.0.0.1:8765
```

## Run a Diagnostic Turn

Use the proving host for a text-only diagnostic turn:

```powershell
.\backend\.venv\Scripts\python scripts\run_jarvis.py --text-only --turns 1
```

`scripts\run_jarvis.py` is a developer and diagnostic surface. The durable application surface is the desktop shell.

## Run the Desktop Shell

Install desktop dependencies:

```powershell
npm --prefix desktop install
```

Run the desktop shell:

```powershell
npm --prefix desktop run dev
```

Do not install Tauri globally for this repository. Use the repo-local desktop dependencies.

## Hardware Notes

Setup is hardware-aware through `backend\app\hardware\profiler.py`, `backend\app\hardware\provisioning.py`, and `backend\app\hardware\preflight.py`. Do not bypass those paths with manual dependency installs.

Local `llama.cpp` support can use repo-managed model artifacts and locally staged runtime sidecars. Most setup does not require manual accelerator work. Windows ARM64 Qualcomm Adreno OpenCL sidecar build notes are available in `docs\jarvis-arm-llamacpp.md` when that specific optional path is needed.

## Development Commands

Run unit tests:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py unit
```

Run integration tests:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py integration
```

Run CI-safe validation:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py ci
```

Run the desktop static test:

```powershell
npm --prefix desktop test
```

## Repository Rules That Matter During Setup

- `pyproject.toml` is the Python dependency source of truth.
- `backend\requirements.txt` is generated and must not be edited by hand.
- `scripts\provision.py` is the only Python dependency installation path.
- Model artifacts live under `models\`.
- Runtime artifacts and caches stay out of source control.
- Validation claims require command evidence.

## Developer Requirements

Install or verify these tools before making code changes:

- Git for clone, branch, diff, and contribution workflow.
- Python `>=3.11` through the Windows `py` launcher.
- Node.js and npm for `desktop/`.
- Rust toolchain for the Tauri desktop shell.
- Tauri system prerequisites for Windows desktop development.
- Docker Desktop for Redis and SearXNG-backed workflows.
- A code editor that can use the repository virtual environment at `backend\.venv`.

Python developer tools are installed by repository provisioning. Do not install them globally:

- `pytest`
- `pytest-cov`
- `pytest-asyncio`
- `ruff`
- `mypy`
- `pre-commit`

Use these repo-owned commands to confirm the development environment:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py verify
.\backend\.venv\Scripts\python scripts\validate_backend.py ci
npm --prefix desktop test
```

Optional tools depend on the area being changed:

- Visual Studio Build Tools or Visual Studio Community with C++ tooling for native Windows runtime work.
- CMake, Ninja, and LLVM for manual native runtime builds.
- Qualcomm/Adreno-specific setup from `docs\jarvis-arm-llamacpp.md` only when working on that optional Windows ARM64 local `llama.cpp` sidecar path.
- Docker Compose when changing or validating local service substrate behavior.
