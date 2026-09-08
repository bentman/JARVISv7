# Operations Guide

Shared operational reference for JARVISv7 setup, troubleshooting, model configuration, optional services, and validation.

Start with the platform QuickStart first:

- [QuickStart-windows.md](QuickStart-windows.md)
- [QuickStart-linux.md](QuickStart-linux.md)

## Command Ownership

- Python dependency authority: `pyproject.toml`
- Generated base requirements: `backend/requirements.txt`
- Python setup/provisioning: `scripts/provision.py`
- Model and runtime artifacts: `scripts/ensure_models.py`
- Backend validation: `scripts/validate_backend.py`
- Desktop commands: `npm --prefix desktop ...`

Use the repo venv Python for repository commands:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py verify
```

```bash
backend/.venv/bin/python scripts/provision.py verify
```

Do not install Python packages globally. Do not hand-edit `backend/requirements.txt`; regenerate it with:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py lock
```

```bash
backend/.venv/bin/python scripts/provision.py lock
```

## Host-Class Support

Host-class support means JARVIS has researched and wired the expected configuration shape for a targeted class: dependency extras, model/runtime profile, readiness behavior, CPU fallback, and deterministic skip or degraded reasons.

Validation is separate. A host-class path is proven only when it has command evidence from matching hardware. Do not skip host-class configuration just because the current machine cannot validate it; label it unvalidated until hardware is available.

## Configuration

Use `.env` for operator configuration. `.env.example` is the starter template.

Configuration load order:

1. Existing process environment values.
2. `.env`, preserving existing process values.
3. `.env.example` when `.env` is absent.
4. Defaults in `backend/app/core/settings.py`.

Common starter settings:

```dotenv
USE_LOCAL_MODEL=true
LLM_MODEL_MODE=dev
LLM_MODEL_POLICY=auto
LLM_MODEL_ID=
USE_OLLAMA=false
OLLAMA_MODEL=phi4-mini
USE_SEARXNG=false
USE_DDGS=true
USE_TAVILY=false
TAVILY_API_KEY=
```

Keep `LLM_MODEL_ID` blank for normal `dev` or `prod` model selection. A nonblank value is an explicit catalog-model override.

## Bootstrap Checkpoints

`scripts/bootstrap.py` runs five ordered checkpoints and stops at the first failure:

| # | Checkpoint | Operation |
|---|---|---|
| 1 | `profile` | Load hardware profile and resolve provisioning extras. |
| 2 | `provision` | Run `scripts/provision.py install`. |
| 3 | `ensure_models` | Acquire configured model families and managed LLM runtime. |
| 4 | `preflight` | Check STT, TTS, LLM, wake, and probe errors. |
| 5 | `validate_profile` | Run `scripts/validate_backend.py profile`. |

Inspect dependency resolution without changing the environment:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py explain
.\backend\.venv\Scripts\python scripts\provision.py dry-run
```

```bash
backend/.venv/bin/python scripts/provision.py explain
backend/.venv/bin/python scripts/provision.py dry-run
```

## Model Providers

Open **Settings -> Model Providers** in the desktop app.

1. Create or select a profile.
2. Enter endpoint, model ID, context window, timeout, and credential when applicable.
3. Use **Test connection** to discover models, or enter a model manually.
4. Select one primary profile and, if needed, a local fallback.
5. To allow local-to-cloud or explicit cloud escalation, select a cloud profile and enable **Allow cloud escalation**.
6. Save and restart the backend when prompted.

Provider credentials are encrypted in `data/operator.sqlite`. The first credential save generates `JARVIS_SECRET_STORE_KEY` in `.env`; do not replace it while encrypted credentials exist.

`.env.example` ships `LLAMA_CPP_MANAGED` blank, which is not the same as `false`. Blank means the managed sidecar follows `USE_LOCAL_MODEL`, so a fresh clone serves its own model from `runtimes/llama.cpp` with no external process. An explicit `false` opts out of that and points the backend at `LLAMA_CPP_BASE_URL`, which reports the `llm` family unready if nothing is listening there.

Before a Model Providers selection is saved, `.env` remains the compatibility authority. For an externally owned llama.cpp or Unsloth OpenAI-compatible server:

```dotenv
LLAMA_CPP_MANAGED=false
LLAMA_CPP_BASE_URL=http://127.0.0.1:8888/v1
LLAMA_CPP_MODEL_NAME=unsloth-model
LLAMA_CPP_CONTEXT_SIZE=32768
```

Both `http://127.0.0.1:8888` and `http://127.0.0.1:8888/v1` are accepted. Ollama turns use `/api/chat`; `OLLAMA_KEEP_ALIVE` defaults to `5m`.

## Model Acquisition

`scripts/ensure_models.py` manages `stt`, `tts`, `wake`, and `llm` model families.

Verify one family:

```powershell
.\backend\.venv\Scripts\python scripts\ensure_models.py --family llm --verify-only
.\backend\.venv\Scripts\python scripts\ensure_models.py --family stt --verify-only
.\backend\.venv\Scripts\python scripts\ensure_models.py --family tts --verify-only
.\backend\.venv\Scripts\python scripts\ensure_models.py --family wake --verify-only
```

```bash
backend/.venv/bin/python scripts/ensure_models.py --family llm --verify-only
backend/.venv/bin/python scripts/ensure_models.py --family stt --verify-only
backend/.venv/bin/python scripts/ensure_models.py --family tts --verify-only
backend/.venv/bin/python scripts/ensure_models.py --family wake --verify-only
```

Remove `--verify-only` to acquire a missing or mismatched artifact.

The default `dev` LLM mode selects the portable Qwen3 4B behavioral model. `prod` selects the host- and policy-matched Qwen3 catalog model.

Preview or acquire production local LLM mode:

```powershell
$env:LLM_MODEL_MODE = "prod"
.\backend\.venv\Scripts\python scripts\ensure_models.py --family llm --dry-run
.\backend\.venv\Scripts\python scripts\ensure_models.py --family llm
```

```bash
export LLM_MODEL_MODE=prod
backend/.venv/bin/python scripts/ensure_models.py --family llm --dry-run
backend/.venv/bin/python scripts/ensure_models.py --family llm
```

Use `--all-llm` only when intentionally validating the full LLM catalog.

## Optional Local Services

Redis and SearXNG are optional. Bootstrap does not install or start Docker, Redis, or SearXNG.

The backend runs without them:

- Redis unavailable: cache-backed behavior is skipped or reported unavailable.
- SearXNG disabled/unavailable: local SearXNG search is skipped; enabled search providers continue in configured order.

The configured search provider order is DDGS, SearXNG, then Tavily. Defaults:

```dotenv
USE_DDGS=true
USE_SEARXNG=false
USE_TAVILY=false
TAVILY_API_KEY=
```

`docker-compose.yml` exposes:

- Redis on `127.0.0.1:${REDIS_PORT:-6379}`
- SearXNG on `127.0.0.1:${SEARXNG_PORT:-8910}`

`config/search/searxng/settings.yml` is the mounted SearXNG settings file.

Start or stop optional services:

```powershell
docker compose up --detach
docker compose down
```

```bash
docker compose up --detach
docker compose down
```

## Backend Diagnostics

Run the backend directly only for API development or diagnosis:

```powershell
.\backend\.venv\Scripts\python scripts\run_backend.py
```

```bash
backend/.venv/bin/python scripts/run_backend.py
```

Default URL:

```text
http://127.0.0.1:8765
```

Text diagnostic:

```powershell
.\backend\.venv\Scripts\python scripts\run_jarvis.py --text-only --turns 1
```

```bash
backend/.venv/bin/python scripts/run_jarvis.py --text-only --turns 1
```

Profile diagnostic:

```powershell
.\backend\.venv\Scripts\python scripts\run_jarvis.py --profile
```

```bash
backend/.venv/bin/python scripts/run_jarvis.py --profile
```

Voice diagnostic requires working STT, TTS, microphone, and audio output:

```powershell
.\backend\.venv\Scripts\python scripts\run_jarvis.py --voice-only --turns 1
```

```bash
backend/.venv/bin/python scripts/run_jarvis.py --voice-only --turns 1
```

## Development Validation

Environment and readiness:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py verify
.\backend\.venv\Scripts\python scripts\validate_backend.py profile
```

```bash
backend/.venv/bin/python scripts/provision.py verify
backend/.venv/bin/python scripts/validate_backend.py profile
```

Repository validation:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py unit
.\backend\.venv\Scripts\python scripts\validate_backend.py integration
.\backend\.venv\Scripts\python scripts\validate_backend.py runtime
.\backend\.venv\Scripts\python scripts\validate_backend.py ci
npm --prefix desktop test
npm --prefix desktop run build
```

```bash
backend/.venv/bin/python scripts/validate_backend.py unit
backend/.venv/bin/python scripts/validate_backend.py integration
backend/.venv/bin/python scripts/validate_backend.py runtime
backend/.venv/bin/python scripts/validate_backend.py ci
npm --prefix desktop test
npm --prefix desktop run build
```

Live tests are gated behind hardware/service availability and are off by default.

```powershell
$env:JARVISV7_LIVE_TESTS = "1"
```

```bash
export JARVISV7_LIVE_TESTS=1
```

## Common Fixes

Python version rejected:

```text
Use a Python version allowed by `pyproject.toml`, then recreate `backend/.venv`.
```

Provisioning failed:

```powershell
.\backend\.venv\Scripts\python scripts\provision.py explain
.\backend\.venv\Scripts\python scripts\provision.py install
```

```bash
backend/.venv/bin/python scripts/provision.py explain
backend/.venv/bin/python scripts/provision.py install
```

Models missing:

```powershell
.\backend\.venv\Scripts\python scripts\ensure_models.py
```

```bash
backend/.venv/bin/python scripts/ensure_models.py
```

Backend starts but readiness is degraded:

```powershell
.\backend\.venv\Scripts\python scripts\validate_backend.py profile
```

```bash
backend/.venv/bin/python scripts/validate_backend.py profile
```

Desktop shell fails before app launch:

```powershell
npm --prefix desktop install
npm --prefix desktop test
```

```bash
npm --prefix desktop install
npm --prefix desktop test
```

## Windows Desktop Build Requirements

Visual Studio and MSVC are required when Windows must compile the Tauri desktop shell from source, including a clean checkout with no existing Tauri build output or a checkout containing Rust changes.

Install the C++ build workload when needed:

```powershell
winget install --exact --id Microsoft.VisualStudio.2022.BuildTools --source winget --override "--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
```

Windows x64 needs Rust stable, Node.js LTS, MSVC C++ build tools, and WebView2.

Windows ARM64 needs Rust stable, native ARM64 Node.js where available, MSVC C++ ARM64 build tools, and WebView2.

## Windows ARM64 Helpers

Provisioning and model selection choose matching host extras and default runtimes automatically. CPU inference needs no accelerator helper.

Use helper docs only when you intentionally need Qualcomm QNN NPU or Adreno OpenCL acceleration:

| Helper | Execution host | Output consumed by JARVIS |
|---|---|---|
| `docs\helpers\jarvis-arm-llamacpp.md` | Windows ARM64 Snapdragon target | `runtimes\llama.cpp\windows-arm64-adreno-opencl\llama-server.exe` and `OpenCL.dll` |
| `docs\helpers\jarvis-arm-whisper.md` | Windows AMD64 preparation host, then Windows ARM64 staging and validation | `models\stt\whisper-qualcomm-qnn` |

Generated runtime binaries and model artifacts stay out of source commits.

## Linux Audio And WSL

Linux and WSL runs need a graphical session and visible audio devices.

Inspect WSL display bridge:

```bash
printf 'DISPLAY=%s\nWAYLAND_DISPLAY=%s\n' "$DISPLAY" "$WAYLAND_DISPLAY"
```

Inspect audio device visibility:

```bash
pactl info
pactl list short sources
pactl list short sinks
backend/.venv/bin/python -m sounddevice
```

Inspect PipeWire:

```bash
systemctl --user --no-pager status pipewire pipewire-pulse wireplumber
```

On PulseAudio-only hosts:

```bash
systemctl --user --no-pager status pulseaudio
```

Device visibility does not prove STT, TTS, wake, interruption, or a completed voice turn; validate those separately.

## Ubuntu 22.04 Python

Ubuntu 22.04 ships Python 3.10 as the system interpreter. Preserve `/usr/bin/python3` for distribution tools and install a supported interpreter side by side.

Build Python 3.12.10 as one supported option:

```bash
sudo apt-get update
sudo apt-get install --yes build-essential pkg-config curl ca-certificates xz-utils libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev libffi-dev liblzma-dev libncursesw5-dev tk-dev uuid-dev libasound2-plugins
cd /tmp
curl --fail --location --remote-name https://www.python.org/ftp/python/3.12.10/Python-3.12.10.tar.xz
tar --extract --file Python-3.12.10.tar.xz
cd Python-3.12.10
./configure --prefix=/usr/local --with-ensurepip=install --enable-optimizations
make -j"$(nproc)"
sudo make altinstall
```

Create the repo venv:

```bash
/usr/local/bin/python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python --version
```

## Additional Linux Desktop Packages

For distributions not covered in QuickStart:

openSUSE:

```bash
sudo zypper up
sudo zypper in webkit2gtk3-devel libopenssl-devel curl wget file libappindicator3-1 librsvg-devel
sudo zypper in -t pattern devel_basis
```

Alpine:

```bash
sudo apk add build-base webkit2gtk-4.1-dev curl wget file openssl libayatana-appindicator-dev librsvg font-dejavu
```

## Linux AMD64 NVIDIA CUDA Runtime

CPU inference needs no CUDA setup. Use this only when intentionally staging the Linux AMD64 CUDA llama.cpp runtime.

The managed CUDA serve profile is pinned by `config/models/llm.yaml` and `docs/helpers/jarvis-wsl-llamacpp.md`:

| Input | Configured value |
|---|---|
| llama.cpp release | `b9704` |
| llama.cpp commit | `10786217e9d40c848ac0133cbe9c5f22a52421bb` |
| Source SHA-256 | `bb288a8045a8fda3fc3be6ffa0e02161ed70d45788b360107fba55a331f93741` |
| Default CUDA Toolkit | `/usr/local/cuda-12.4` |
| CUDA architecture | `86` |
| Staged runtime | `runtimes/llama.cpp/linux-amd64-cuda` |

Build and stage the runtime:

```bash
bash docs/helpers/jarvis-wsl-llamacpp.sh --install-cuda-toolkit
bash docs/helpers/jarvis-wsl-llamacpp.sh
```

Validate:

```bash
backend/.venv/bin/python scripts/validate_backend.py profile
backend/.venv/bin/python scripts/ensure_models.py --family llm --verify-only
backend/.venv/bin/python scripts/validate_backend.py runtime --families llm --devices cuda
```
