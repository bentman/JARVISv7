# Quick Start - Linux / WSL

Use this guide to get a fresh clone running from source on a graphical Linux desktop or WSL 2 with WSLg.

For operational details, diagnostics, model-provider setup, optional services, and platform appendices, use [OperationsGuide.md](OperationsGuide.md).

## Requirements

Install the package block for your distribution.

Ubuntu 24.04 or Debian 12:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
sudo apt install -y git curl wget file nodejs npm libportaudio2 libasound2-plugins pulseaudio-utils
sudo apt install -y build-essential pkg-config libssl-dev libgtk-3-dev libwebkit2gtk-4.1-dev libayatana-appindicator3-dev librsvg2-dev libxdo-dev
```

Fedora:

```bash
sudo dnf group install -y "c-development"
sudo dnf install -y python3 python3-pip
sudo dnf install -y git curl wget file nodejs npm portaudio openssl-devel webkit2gtk4.1-devel libappindicator-gtk3-devel librsvg2-devel libxdo-devel
```

Arch Linux:

```bash
sudo pacman -Syu --needed python
sudo pacman -S --needed git curl wget file nodejs npm portaudio base-devel openssl webkit2gtk-4.1 appmenu-gtk-module libappindicator-gtk3 librsvg xdotool
```

Install Rust through `rustup`:

```bash
curl --proto '=https' --tlsv1.2 https://sh.rustup.rs -sSf | sh -s -- -y
source "$HOME/.cargo/env"
```

Close and reopen the terminal after installation.

Python support targets 3.11 through 3.14. `pyproject.toml` is the dependency and interpreter authority for installs; if a Python version is rejected during setup, the range enforced there wins. Some distributions ship an older Python, so install a supported interpreter side by side when needed.

For WSL:

```powershell
wsl --install
```

Run that once in Administrator PowerShell for a new WSL installation, restart Windows, then use the Ubuntu instructions in the Linux terminal. If WSL graphical apps do not open:

```powershell
wsl --update
wsl --shutdown
```

## Avoid Gotchas

- Use the repository root as the working directory.
- Use `backend/.venv/bin/python` for repo Python commands after the venv exists.
- Use `npm --prefix desktop ...` for desktop commands.
- Keep `LLM_MODEL_ID` blank unless you intentionally want a fixed catalog model.
- Use `.env` for local configuration. Do not edit `.env.example` for operator changes.
- WSL and Linux desktop runs need a working graphical session and visible audio input/output devices.
- Optional Docker services are not required for first run; the app runs without them and dependent features report unavailable or degraded state.

## First Run

Clone the repo:

```bash
git clone https://github.com/bentman/JARVISv7.git
cd JARVISv7
```

For an existing clone:

```bash
cd <REPO_ROOT_PATH>
git pull
```

Prepare local environment files and caches:

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
if [[ ! -f .env ]]; then cp .env.example .env; fi
```

Create the backend virtual environment:

```bash
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
```

Install Python dependencies, acquire configured models and runtime artifacts, and run startup checks:

```bash
backend/.venv/bin/python scripts/bootstrap.py
```

Install desktop dependencies:

```bash
npm --prefix desktop install
```

Launch the desktop:

```bash
npm --prefix desktop run dev
```

Keep that terminal open. The desktop starts and stops the backend automatically.

## What Bootstrap Does

`scripts/bootstrap.py` runs the first-run backend setup sequence:

1. Profile the host hardware.
2. Resolve and install the matching Python dependency extras.
3. Acquire configured STT, TTS, wake, LLM model, and managed runtime artifacts.
4. Run preflight checks for runtime readiness.
5. Run `scripts/validate_backend.py profile`.

Each checkpoint prints `PASS` or `FAIL`. Use the failed checkpoint name with [OperationsGuide.md](OperationsGuide.md#common-fixes) when setup does not complete.

## Optional Components

Redis and SearXNG are available through `docker-compose.yml`, but they are not required for the app to launch.

- Redis backs optional cache/service substrate.
- SearXNG provides an optional local metasearch provider.
- If either service is absent, dependent features safely skip usage or report unavailable/degraded state.

To start them after Docker is installed:

```bash
docker compose up --detach
```

To stop them:

```bash
docker compose down
```

See [OperationsGuide.md](OperationsGuide.md#optional-local-services) for provider settings and ports.

## Quick Checks

Environment/readiness:

```bash
backend/.venv/bin/python scripts/provision.py verify
backend/.venv/bin/python scripts/validate_backend.py profile
```

Desktop static check:

```bash
npm --prefix desktop test
```

Answering check - the one that proves the assistant actually serves, which a passing suite does not:

```bash
backend/.venv/bin/python scripts/run_backend.py --host 127.0.0.1 --port 8730
# in a second shell
curl -s http://127.0.0.1:8730/readiness            # families.llm.ready must be true
curl -s -X POST http://127.0.0.1:8730/session/create -H 'content-type: application/json' -d '{}'
curl -s -X POST http://127.0.0.1:8730/task/text -H 'content-type: application/json' \
  -d '{"text":"Reply with one word: WORKING"}'     # response_text must come back
```

If `families.llm.ready` is false, read its `reason`. `LLAMA_CPP_MANAGED=false` in `.env` with no
external server listening at `LLAMA_CPP_BASE_URL` is the usual cause; leave the key blank to use
the managed sidecar.

## When You Need More

- Model providers, Ollama, cloud escalation, and credentials: [OperationsGuide.md](OperationsGuide.md#model-providers)
- Model artifact repair: [OperationsGuide.md](OperationsGuide.md#model-acquisition)
- Backend diagnostics: [OperationsGuide.md](OperationsGuide.md#backend-diagnostics)
- Validation tiers: [OperationsGuide.md](OperationsGuide.md#development-validation)
- Linux audio and WSL diagnosis: [OperationsGuide.md](OperationsGuide.md#linux-audio-and-wsl)
- Ubuntu 22.04 Python setup: [OperationsGuide.md](OperationsGuide.md#ubuntu-2204-python)
- Linux CUDA llama.cpp runtime: [OperationsGuide.md](OperationsGuide.md#linux-amd64-nvidia-cuda-runtime)
