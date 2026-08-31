# Quick Start - Windows

Use this guide to get a fresh clone running from source on Windows 10 or 11.

For operational details, diagnostics, model-provider setup, optional services, and platform appendices, use [OperationsGuide.md](OperationsGuide.md).

## Requirements

Install the normal source-run prerequisites:

```powershell
winget install --exact --id Git.Git --source winget
winget install --exact --id Python.Python.3.11 --source winget
winget install --exact --id OpenJS.NodeJS.LTS --source winget
winget install --exact --id Rustlang.Rustup --source winget
winget install --exact --id Microsoft.EdgeWebView2Runtime --source winget
```

Close and reopen PowerShell after installation.

Python support targets 3.11 through 3.14. `pyproject.toml` is the dependency and interpreter authority for installs; if a Python version is rejected during setup, the range enforced there wins. Python 3.11 is the lowest-friction first-run choice.

The desktop source run uses repo-local Tauri dependencies. Do not install Tauri globally.

## Avoid Gotchas

- Use PowerShell from the repository root.
- Use `backend\.venv\Scripts\python` for repo Python commands after the venv exists.
- Use `npm --prefix desktop ...` for desktop commands.
- Keep `LLM_MODEL_ID` blank unless you intentionally want a fixed catalog model.
- Use `.env` for local configuration. Do not edit `.env.example` for operator changes.
- Keep temp and package caches under `cache\` to avoid Windows sandbox, temp, and file-lock friction.
- Optional Docker services are not required for first run; the app runs without them and dependent features report unavailable or degraded state.

## First Run

Clone the repo:

```powershell
git clone https://github.com/bentman/JARVISv7.git
Set-Location .\JARVISv7
```

For an existing clone:

```powershell
Set-Location <REPO_ROOT_PATH>
git pull
```

Prepare local environment files and caches:

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$repoRoot = (git rev-parse --show-toplevel).Trim()
$env:TEMP = "$repoRoot\cache\temp"
$env:TMP = "$repoRoot\cache\temp"
$env:TMPDIR = "$repoRoot\cache\temp"
$env:PIP_CACHE_DIR = "$repoRoot\cache\pip"
New-Item -ItemType Directory -Force $env:TEMP, $env:PIP_CACHE_DIR | Out-Null
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Create the backend virtual environment:

```powershell
py -3.11 -m venv backend\.venv
.\backend\.venv\Scripts\python -m pip install --upgrade pip
```

Install Python dependencies, acquire configured models and runtime artifacts, and run startup checks:

```powershell
.\backend\.venv\Scripts\python scripts\bootstrap.py
```

Install desktop dependencies:

```powershell
npm --prefix desktop install
```

Launch the desktop:

```powershell
npm --prefix desktop run dev
```

Keep that PowerShell window open. The desktop starts and stops the backend automatically.

## What Bootstrap Does

`scripts\bootstrap.py` runs the first-run backend setup sequence:

1. Profile the host hardware.
2. Resolve and install the matching Python dependency extras.
3. Acquire configured STT, TTS, wake, LLM model, and managed runtime artifacts.
4. Run preflight checks for runtime readiness.
5. Run `scripts\validate_backend.py profile`.

Each checkpoint prints `PASS` or `FAIL`. Use the failed checkpoint name with [OperationsGuide.md](OperationsGuide.md#common-fixes) when setup does not complete.

## Optional Components

Redis and SearXNG are available through `docker-compose.yml`, but they are not required for the app to launch.

- Redis backs optional cache/service substrate.
- SearXNG provides an optional local metasearch provider.
- If either service is absent, dependent features safely skip usage or report unavailable/degraded state.

To start them after Docker is installed:

```powershell
docker compose up --detach
```

To stop them:

```powershell
docker compose down
```

See [OperationsGuide.md](OperationsGuide.md#optional-local-services) for provider settings and ports.

## Quick Checks

Environment/readiness:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py verify
.\backend\.venv\Scripts\python scripts\validate_backend.py profile
```

Desktop static check:

```powershell
npm --prefix desktop test
```

## When You Need More

- Model providers, Ollama, cloud escalation, and credentials: [OperationsGuide.md](OperationsGuide.md#model-providers)
- Model artifact repair: [OperationsGuide.md](OperationsGuide.md#model-acquisition)
- Backend diagnostics: [OperationsGuide.md](OperationsGuide.md#backend-diagnostics)
- Validation tiers: [OperationsGuide.md](OperationsGuide.md#development-validation)
- Windows ARM64/QNN/OpenCL paths: [OperationsGuide.md](OperationsGuide.md#windows-arm64-helpers)
- Desktop build prerequisites: [OperationsGuide.md](OperationsGuide.md#windows-desktop-build-requirements)
