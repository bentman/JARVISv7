# JARVIS Linux AMD64/WSL2 llama.cpp CUDA Build

## Purpose

`docs/jarvis-wsl-llamacpp.sh` builds the pinned llama.cpp CUDA sidecar for Linux AMD64/WSL2 and stages only a validated runtime into:

```text
runtimes/llama.cpp/linux-amd64-cuda
```

This is a verified Linux AMD64 NVIDIA CUDA path. WSL2 was the proving environment, not a separate runtime identifier.

Source, build trees, failed stages, previous-runtime backups, locks, and transcripts remain outside the repository under:

```text
~/WORK/CODE/jarvis-dev/llamacpp-cuda
```

## Pinned inputs

| Input | Value |
|---|---|
| llama.cpp tag | `b9704` |
| llama.cpp commit | `10786217e9d40c848ac0133cbe9c5f22a52421bb` |
| llama.cpp build number | `9704` |
| Default CUDA Toolkit | `/usr/local/cuda-12.4` |
| CUDA architecture | `86` (RTX 3060/Ampere) |
| Generator | Ninja |
| Build type | Release |
| Shared libraries | Enabled |

## Why CUDA 12.4 is the default

On the target WSL2 host, two clean source builds with CUDA 13.3 completed successfully and linked entirely against the intended build-tree and CUDA 13.3 libraries, but both aborted before model loading when executing `llama-server --version`:

```text
munmap_chunk(): invalid pointer
exit 134
```

The same pre-model failure pattern has been reported upstream for WSL2 CUDA 13.x builds. The JARVIS helper therefore fails closed on CUDA 13.x and uses CUDA 12.4 as the qualified WSL build path.

A newer NVIDIA driver can run applications built with an older CUDA Toolkit through CUDA driver backward compatibility. Installing `cuda-toolkit-12-4` does not replace the Windows/WSL NVIDIA driver. Side-by-side Toolkit installations are supported.

## Install or select CUDA 12.4

When the NVIDIA CUDA apt repository is already configured:

```bash
bash docs/jarvis-wsl-llamacpp.sh --install-cuda-toolkit
```

The helper installs only:

```text
cuda-toolkit-12-4
```

It does not install `cuda`, `cuda-runtime-*`, or `cuda-drivers` packages.

To use an existing compatible CUDA 12.x Toolkit explicitly:

```bash
bash docs/jarvis-wsl-llamacpp.sh --cuda-root /usr/local/cuda-12.4
```

The selected root must contain `bin/nvcc`, `include`, and `lib64`. CUDA 13.x roots are rejected before configuration so the known-bad build is not repeated.

## Run

From the JARVIS repository root:

```bash
bash docs/jarvis-wsl-llamacpp.sh --install-cuda-toolkit
```

After CUDA 12.4 exists, normal reruns use:

```bash
bash docs/jarvis-wsl-llamacpp.sh
```

Optional arguments:

```text
--jarvis-root PATH
--dev-root PATH
--cuda-root PATH
--transcript PATH
--install-build-prereqs
--install-cuda-toolkit
--keep-previous-runtime
```

## Determinism and failure handling

The helper:

- verifies the pinned tag, commit, and Git-derived build number;
- uses a CUDA-version-specific external build directory;
- fingerprints the source, compiler, CUDA root/version, architecture, CMake, and build configuration;
- discards only an incompatible external CMake tree;
- uses the selected Toolkit `lib64` directory plus `$ORIGIN` in the build/install RPATH;
- preserves shared-library symlinks while staging;
- captures and prints native probe failures;
- preserves failed stages under `~/WORK/CODE/jarvis-dev/llamacpp-cuda/failed-stage-*`;
- replaces the installed runtime only after all staged checks pass.

## Required staged evidence

The stage must contain:

```text
llama-server
libllama-server-impl.so
libllama-common.so.0
libggml.so
libggml-base.so
libggml-cpu.so
libggml-cuda.so
libllama.so
libmtmd.so
```

Before installation, the helper requires:

- `llama-server --version` exits successfully and reports build `9704` and commit `10786217`;
- `llama-server --list-devices` exits successfully and enumerates CUDA or the RTX 3060;
- llama.cpp libraries resolve from the stage;
- `libcudart` and cuBLAS resolve from the selected CUDA 12.x root;
- `libcuda.so.1` resolves from `/usr/lib/wsl/lib/libcuda.so.1`;
- no shared library is unresolved.

## Production model and runtime closeout

The helper verifies only the selected production LLM:

```bash
backend/.venv/bin/python scripts/ensure_models.py --family llm --verify-only
```

After the helper reports `PASS`:

```bash
backend/.venv/bin/python scripts/validate_backend.py profile
backend/.venv/bin/python scripts/ensure_models.py --family llm --verify-only
backend/.venv/bin/python scripts/validate_backend.py runtime --families llm --devices cuda
```

Managed production validation completed with the selected balanced GGUF: the sidecar started, health and `/v1/models` succeeded, a real completion succeeded with CUDA GPU-layer offload, and cleanup left no `llama-server` process. Reproduce the focused live proof with:

```bash
JARVISV7_LIVE_TESTS=true backend/.venv/bin/python scripts/validate_backend.py runtime --families llm --devices cuda
```

This verification applies only to Linux AMD64 NVIDIA CUDA with the staged runtime above; it does not establish other Linux accelerators or desktop/audio paths.

## Cleanup boundaries

The helper may remove only:

- its CUDA-version-specific external CMake build tree when the fingerprint changes;
- abandoned `runtimes/llama.cpp/linux-amd64-cuda.stage.*` directories;
- the previous managed CUDA runtime after successful replacement unless `--keep-previous-runtime` is supplied.

It does not remove models, the Linux CPU runtime, CUDA 13.3, NVIDIA drivers, or unrelated developer workspaces.
