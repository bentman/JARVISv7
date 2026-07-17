# JARVIS WSL llama.cpp NVIDIA CUDA

Build and stage the managed `linux_amd64_gpu_nvidia_cuda` llama.cpp sidecar on Linux AMD64/WSL2.

## Host requirements

- NVIDIA GPU passthrough works in WSL2.
- CUDA Toolkit 13.3 exists at `/usr/local/cuda-13.3`.
- CMake, GCC/G++, curl, tar, binutils, and the repository virtual environment are available.

The helper selects CUDA 13.3 for its own process before any checks or build commands:

```text
PATH=/usr/local/cuda-13.3/bin:...
LD_LIBRARY_PATH=/usr/local/cuda-13.3/lib64:...
CUDA_HOME=/usr/local/cuda-13.3
CUDACXX=/usr/local/cuda-13.3/bin/nvcc
```

It does not persist shell settings or change the system CUDA selection.

## Pinned source

```text
release/tag: b9704
commit:      10786217e9d40c848ac0133cbe9c5f22a52421bb
archive:     https://github.com/ggml-org/llama.cpp/archive/refs/tags/b9704.tar.gz
SHA-256:     bb288a8045a8fda3fc3be6ffa0e02161ed70d45788b360107fba55a331f93741
```

Source and build data remain under:

```text
cache/llama.cpp/linux_amd64_gpu_nvidia_cuda/
```

The staged runtime is:

```text
runtimes/llama.cpp/linux-amd64-cuda/
```

## Run

From the repository root:

```bash
docs/jarvis-wsl-llamacpp.sh
```

To discard only the generated CMake build cache before rebuilding:

```bash
docs/jarvis-wsl-llamacpp.sh --clean-build
```

The optional `--install-build-prereqs` installs only missing generic build tools. It never installs or changes NVIDIA drivers or CUDA packages.

## Build behavior

The helper builds only `llama-server` with:

```text
GGML_CUDA=ON
CMAKE_BUILD_TYPE=Release
CMAKE_CUDA_ARCHITECTURES=86
CMAKE_BUILD_RPATH_USE_ORIGIN=ON
CMAKE_BUILD_RPATH=$ORIGIN
CMAKE_INSTALL_RPATH=$ORIGIN
```

`$ORIGIN` makes `llama-server` load the llama.cpp shared libraries beside the executable in the staged runtime directory. It must not resolve them from `cache/.../build/bin`.

The helper stages the server and all adjacent `.so`/`.so.*` files, then checks:

- the executable RUNPATH contains `$ORIGIN`;
- `ldd` reports no unresolved libraries;
- no dependency resolves from the generated build cache;
- `ensure_models.py --family llm --verify-only` accepts the staged runtime.

Expected `ldd` results for llama.cpp libraries must point under:

```text
runtimes/llama.cpp/linux-amd64-cuda/
```

The WSL driver library should resolve as:

```text
libcuda.so.1 => /usr/lib/wsl/lib/libcuda.so.1
```

## Validation

After a successful build and stage:

```bash
backend/.venv/bin/python scripts/validate_backend.py runtime --families llm --devices cuda
```

Required outcome evidence:

- `linux_amd64_gpu_nvidia_cuda` is selected;
- managed `llama-server` starts;
- health, model listing, and completion succeed;
- server output proves CUDA device discovery or GPU-layer offload.

Profile selection alone is not GPU proof.

## Recovery

For an interrupted or stale build:

```bash
rm -rf cache/llama.cpp/linux_amd64_gpu_nvidia_cuda/build
docs/jarvis-wsl-llamacpp.sh
```

Do not remove models, the Linux CPU runtime, CUDA installations, drivers, or system packages as part of this recovery.

# Appendix
## Prepend CUDA 3.13 Paths

```bash
export PATH="/usr/local/cuda-13.3/bin:$PATH"
export LD_LIBRARY_PATH="/usr/local/cuda-13.3/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CUDA_HOME="/usr/local/cuda-13.3"
export CUDACXX="/usr/local/cuda-13.3/bin/nvcc"
```