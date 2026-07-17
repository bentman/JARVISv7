#!/usr/bin/env bash
# Build and stage the JARVIS WSL2 Linux AMD64 NVIDIA CUDA llama.cpp sidecar.
#
# Uses the pinned b9704 source archive declared by the JARVIS CUDA profile.
# It never installs or changes NVIDIA drivers, CUDA toolkits, PATH, shell
# files, Docker, or other system configuration.

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
DEFAULT_JARVIS_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
PROFILE_ID="linux_amd64_gpu_nvidia_cuda"
LLAMA_RELEASE="b9704"
LLAMA_COMMIT="10786217e9d40c848ac0133cbe9c5f22a52421bb"
LLAMA_ARCHIVE="llama.cpp-b9704.tar.gz"
LLAMA_URL="https://github.com/ggml-org/llama.cpp/archive/refs/tags/b9704.tar.gz"
LLAMA_SHA256="bb288a8045a8fda3fc3be6ffa0e02161ed70d45788b360107fba55a331f93741"
CUDA_COMPILER="/usr/local/cuda-13.3/bin/nvcc"
CUDA_TOOLKIT_ROOT="/usr/local/cuda-13.3"

jarvis_root="$DEFAULT_JARVIS_ROOT"
install_build_prereqs=false
clean_build=false

usage() {
    cat <<'USAGE'
Usage: docs/jarvis-wsl-llamacpp.sh [options]

Options:
  --jarvis-root PATH       JARVIS repository root.
  --install-build-prereqs  Use sudo to install only missing generic build tools.
  --clean-build            Remove only this profile's generated CMake cache.
  -h, --help               Show this help.

CUDA and NVIDIA packages are never installed or changed by this helper.
USAGE
}

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
run() { printf '+'; printf ' %q' "$@"; printf '\n'; "$@"; }
has() { command -v "$1" >/dev/null 2>&1; }

while (($#)); do
    case "$1" in
        --jarvis-root) (($# >= 2)) || die "--jarvis-root requires a path"; jarvis_root="$2"; shift 2 ;;
        --install-build-prereqs) install_build_prereqs=true; shift ;;
        --clean-build) clean_build=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

[[ -d "$jarvis_root" ]] || die "JARVIS root does not exist: $jarvis_root"
jarvis_root="$(cd -- "$jarvis_root" && pwd)"
[[ -f "$jarvis_root/config/models/llm.yaml" ]] || die "Not a JARVIS repository: $jarvis_root"

missing=""
has cmake || missing="$missing cmake"
has gcc || missing="$missing build-essential"
has g++ || missing="$missing build-essential"
has curl || missing="$missing curl"
has sha256sum || missing="$missing coreutils"
has tar || missing="$missing tar"
missing="$(printf '%s\n' $missing | awk 'NF && !seen[$0]++')"

if [[ -n "$missing" && "$install_build_prereqs" == true ]]; then
    has apt-get || die "Missing build tools and apt-get is unavailable: $missing"
    log "Elevating with sudo to install missing generic build prerequisites"
    sudo -v
    run sudo apt-get update
    run sudo apt-get install --yes $missing
fi
[[ -z "$missing" || "$install_build_prereqs" == true ]] || die "Missing build tools:$missing. Re-run with --install-build-prereqs."

[[ -x "$CUDA_COMPILER" ]] || die "CUDA 13.3 compiler unavailable: $CUDA_COMPILER"
[[ -d "$CUDA_TOOLKIT_ROOT/include" ]] || die "CUDA 13.3 headers unavailable: $CUDA_TOOLKIT_ROOT/include"
[[ -x "$jarvis_root/backend/.venv/bin/python" ]] || die "Repository Python unavailable: backend/.venv/bin/python"

log "Verify WSL2 NVIDIA/CUDA readiness"
run nvidia-smi
run "$CUDA_COMPILER" --version
run cmake --version
run gcc --version
run g++ --version
run "$jarvis_root/backend/.venv/bin/python" "$jarvis_root/scripts/validate_backend.py" profile

cache_root="$jarvis_root/cache/llama.cpp/$PROFILE_ID"
archive_path="$cache_root/$LLAMA_ARCHIVE"
source_root="$cache_root/source"
build_root="$cache_root/build"
runtime_root="$jarvis_root/runtimes/llama.cpp/linux-amd64-cuda"
runtime_stage="$runtime_root.stage.$$"

if [[ "$clean_build" == true ]]; then
    log "Remove only this profile's generated CMake build cache"
    rm -rf -- "$build_root"
fi

log "Acquire and verify pinned llama.cpp source"
mkdir -p -- "$cache_root"
if [[ ! -f "$archive_path" ]] || [[ "$(sha256sum "$archive_path" | awk '{print $1}')" != "$LLAMA_SHA256" ]]; then
    rm -f -- "$archive_path.part"
    run curl --fail --location --retry 3 --output "$archive_path.part" "$LLAMA_URL"
    [[ "$(sha256sum "$archive_path.part" | awk '{print $1}')" == "$LLAMA_SHA256" ]] || die "Source archive checksum mismatch"
    mv -- "$archive_path.part" "$archive_path"
fi
printf '%s  %s\n' "$LLAMA_SHA256" "$archive_path" | sha256sum --check

if [[ ! -f "$source_root/.managed-source-commit" ]] || [[ "$(tr -d '\n' < "$source_root/.managed-source-commit")" != "$LLAMA_COMMIT" ]]; then
    log "Extract pinned source into cache"
    rm -rf -- "$source_root"
    mkdir -p -- "$source_root"
    run tar --extract --gzip --file "$archive_path" --strip-components=1 --directory "$source_root" --no-same-owner
    printf '%s\n' "$LLAMA_COMMIT" > "$source_root/.managed-source-commit"
fi

log "Configure CUDA Release build"
run cmake -S "$source_root" -B "$build_root" \
    -DGGML_CUDA=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_COMPILER="$CUDA_COMPILER" \
    -DCUDAToolkit_ROOT="$CUDA_TOOLKIT_ROOT" \
    -DCMAKE_CUDA_ARCHITECTURES=86 \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_TOOLS=ON \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_SERVER=ON \
    -DLLAMA_BUILD_APP=OFF \
    -DLLAMA_BUILD_UI=OFF \
    -DLLAMA_USE_PREBUILT_UI=OFF

log "Build llama-server only"
run cmake --build "$build_root" --config Release --target llama-server

build_bin="$build_root/bin"
[[ -x "$build_bin/llama-server" ]] || die "Build produced no executable: $build_bin/llama-server"

log "Stage executable and adjacent shared libraries"
rm -rf -- "$runtime_stage"
mkdir -p -- "$runtime_stage"
install -m 0755 "$build_bin/llama-server" "$runtime_stage/llama-server"
found_library=false
for library in "$build_bin"/*.so "$build_bin"/*.so.*; do
    [[ -f "$library" ]] || continue
    install -m 0644 "$library" "$runtime_stage/$(basename -- "$library")"
    found_library=true
done
"$found_library" || die "Build produced no adjacent shared libraries"

for required in llama-server libggml.so libggml-base.so libggml-cpu.so libggml-cuda.so libllama.so libmtmd.so; do
    [[ -f "$runtime_stage/$required" ]] || die "Required staged file missing: $required"
done

if [[ -d "$runtime_root" ]]; then
    backup_root="$runtime_root.previous.$(date +%Y%m%d%H%M%S)"
    mv -- "$runtime_root" "$backup_root"
    printf 'Previous runtime moved to: %s\n' "$backup_root"
fi
mv -- "$runtime_stage" "$runtime_root"

log "Verify staged runtime"
run "$jarvis_root/backend/.venv/bin/python" "$jarvis_root/scripts/ensure_models.py" --family llm --verify-only
run ldd "$runtime_root/llama-server"
printf 'Staged runtime: %s\n' "$runtime_root"
printf 'Pinned source: %s (%s), SHA-256 %s\n' "$LLAMA_RELEASE" "$LLAMA_COMMIT" "$LLAMA_SHA256"
printf 'Next: run managed LLM CUDA validation and prove device/layer offload from server output.\n'

