# JARVIS WSL llama.cpp NVIDIA CUDA

This document explains how to build and stage the managed llama.cpp CUDA sidecar for a Linux AMD64 JARVIS installation running under WSL2.

The managed profile is `linux_amd64_gpu_nvidia_cuda`. It builds the pinned llama.cpp `b9704` source archive with CUDA enabled and falls back to `linux_amd64_cpu` when NVIDIA/CUDA readiness or the CUDA sidecar is unavailable.

This process does not install or modify CUDA, NVIDIA drivers, compilers, CMake, PATH, shell files, Docker, or other host configuration.

## Output

The managed build stages only the runtime sidecar files JARVIS consumes:

```text
runtimes/llama.cpp/linux-amd64-cuda/llama-server
runtimes/llama.cpp/linux-amd64-cuda/libggml.so
runtimes/llama.cpp/linux-amd64-cuda/libggml-base.so
runtimes/llama.cpp/linux-amd64-cuda/libggml-cpu.so
runtimes/llama.cpp/linux-amd64-cuda/libggml-cuda.so
runtimes/llama.cpp/linux-amd64-cuda/libllama.so
runtimes/llama.cpp/linux-amd64-cuda/libmtmd.so
```

Do not commit generated runtime binaries. The source archive, extracted source, and CMake build tree stay under:

```text
cache/llama.cpp/linux_amd64_gpu_nvidia_cuda/
```

## Requirements

Run these commands in the WSL2 Linux shell from the JARVIS repository root.

Required:

- Linux AMD64 WSL2 host with NVIDIA GPU passthrough working.
- NVIDIA driver visible inside WSL2.
- CUDA Toolkit 13.3 at `/usr/local/cuda-13.3`.
- CMake and GCC/G++ available in WSL2.
- The repository virtual environment at `backend/.venv`.
- A local GGUF model selected by JARVIS.

Verify the host before starting:

```bash
nvidia-smi
/usr/local/cuda-13.3/bin/nvcc --version
cmake --version
gcc --version
g++ --version
backend/.venv/bin/python scripts/validate_backend.py profile
```

Required profiler evidence includes:

```text
os_name=linux
arch=amd64
gpu_available=true
gpu_vendor=nvidia
cuda_available=true
supports_cuda_llm=true
supports_gpu_llm=true
```

`ep:CUDAExecutionProvider` is not required for llama.cpp CUDA. That is an ONNX Runtime provider capability and remains relevant only to ONNX-backed services.

If `nvidia-smi` fails, the profiler reports `gpu_available=false`, or CUDA 13.3 is not visible at the path above, stop. Fix WSL GPU passthrough or the existing CUDA installation before attempting a JARVIS CUDA build.

## Pinned source provenance

The managed profile uses the official llama.cpp source archive:

```text
release/tag: b9704
commit:      10786217e9d40c848ac0133cbe9c5f22a52421bb
archive:     https://github.com/ggml-org/llama.cpp/archive/refs/tags/b9704.tar.gz
SHA-256:     bb288a8045a8fda3fc3be6ffa0e02161ed70d45788b360107fba55a331f93741
```

The acquisition path verifies the archive SHA-256 before extraction.

## Build and stage

First ensure local-model acquisition is enabled for the normal JARVIS workflow. Do not add a CUDA-specific environment variable.

Run the normal current-host LLM acquisition command without `--model` or `--all-llm`:

```bash
backend/.venv/bin/python scripts/ensure_models.py --family llm
```

On a CUDA-ready Linux AMD64 host, this selects and builds `linux_amd64_gpu_nvidia_cuda`. The managed build performs the equivalent CMake steps:

```bash
cmake -S cache/llama.cpp/linux_amd64_gpu_nvidia_cuda/source \
  -B cache/llama.cpp/linux_amd64_gpu_nvidia_cuda/build \
  -DGGML_CUDA=ON \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CUDA_COMPILER=/usr/local/cuda-13.3/bin/nvcc \
  -DCUDAToolkit_ROOT=/usr/local/cuda-13.3 \
  -DCMAKE_CUDA_ARCHITECTURES=86 \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_TOOLS=ON \
  -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_SERVER=ON \
  -DLLAMA_BUILD_APP=OFF \
  -DLLAMA_BUILD_UI=OFF \
  -DLLAMA_USE_PREBUILT_UI=OFF

cmake --build cache/llama.cpp/linux_amd64_gpu_nvidia_cuda/build \
  --config Release --target llama-server
```

`LLAMA_BUILD_TOOLS=ON` is required by upstream `b9704` because its `llama-server` target is defined below `tools/`; only `llama-server` is built. Tests and examples stay disabled. CUDA architecture `86` targets the RTX 3060.

After acquisition, verify the staged runtime:

```bash
backend/.venv/bin/python scripts/ensure_models.py --family llm --verify-only
find runtimes/llama.cpp/linux-amd64-cuda -maxdepth 1 -type f -printf '%f %m\n' | sort
ldd runtimes/llama.cpp/linux-amd64-cuda/llama-server
```

`llama-server` must be executable and its adjacent llama.cpp `.so` files must remain beside it.

## Managed server proof

Start JARVIS with its normal managed local-model configuration, then prove the managed sidecar rather than a manually started server.

```bash
backend/.venv/bin/python scripts/validate_backend.py runtime --families llm --devices cuda
```

The required live evidence is:

- Resolution selects `linux_amd64_gpu_nvidia_cuda` with `accelerator=gpu.cuda`.
- Managed `llama-server` starts successfully.
- `/health` responds successfully.
- `/models` reports the loaded model.
- A real completion succeeds.
- Server output or backend information directly identifies the CUDA backend/device or GPU layer offload.

Profile selection by itself is not GPU-offload proof. If CUDA backend/device output is absent, treat the result as unvalidated.

## CPU fallback proof

Do not delete the CPU runtime. Temporarily make CUDA readiness unavailable, or move only the CUDA sidecar out of the runtime directory, then run the same managed LLM validation.

Expected evidence:

- Resolution selects `linux_amd64_cpu`.
- The CUDA profile appears as a degraded candidate with a specific reason.
- The CPU managed server completes a request successfully.

Restore the CUDA sidecar after this test. Do not change JARVIS runtime code to mask a failed CUDA build.

## Recovery

The source/build cache is disposable generated data. If a source build is interrupted before staging, remove only the affected generated cache paths and rerun the normal acquisition command:

```bash
rm -rf cache/llama.cpp/linux_amd64_gpu_nvidia_cuda/build
backend/.venv/bin/python scripts/ensure_models.py --family llm
```

If the build reaches the UI-assets step after a prior interrupted attempt and reports a stale/missing `loading.html`, remove only its generated asset directory and retry:

```bash
rm -rf cache/llama.cpp/linux_amd64_gpu_nvidia_cuda/build/tools/ui/dist
backend/.venv/bin/python scripts/ensure_models.py --family llm
```

Do not remove `models/`, `runtimes/llama.cpp/linux-amd64-cpu/`, CUDA installations, drivers, or system packages as part of this recovery.

## Troubleshooting

`nvidia-smi` fails in WSL2:

- Stop; GPU passthrough is unavailable to this shell.
- Restart or repair the Windows/WSL GPU integration outside JARVIS, then repeat the host checks.

CMake reports unsupported `compute_50` with CUDA 13.3:

- Ensure the managed configure includes `-DCMAKE_CUDA_ARCHITECTURES=86`.
- Do not downgrade or replace host CUDA to work around this.

CMake finds CUDA 11.5 while using CUDA 13.3 `nvcc`:

- Ensure the managed configure includes both `-DCMAKE_CUDA_COMPILER=/usr/local/cuda-13.3/bin/nvcc` and `-DCUDAToolkit_ROOT=/usr/local/cuda-13.3`.
- Do not change global `PATH` just for JARVIS.

JARVIS selects CPU after a successful CUDA build:

- Re-run `scripts/validate_backend.py profile` and confirm NVIDIA/CUDA readiness is true.
- Verify the sidecar with `ensure_models.py --family llm --verify-only`.
- Confirm every required `.so` is adjacent to `llama-server` and the executable bit is present.

## References

```text
https://github.com/ggml-org/llama.cpp
https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
https://docs.nvidia.com/cuda/wsl-user-guide/index.html
```

