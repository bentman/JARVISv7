#!/usr/bin/env bash
# Build and stage the JARVIS Linux AMD64/WSL2 NVIDIA CUDA llama.cpp sidecar.

set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_JARVIS_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
DEFAULT_DEV_ROOT="$HOME/WORK/CODE/jarvis-dev/llamacpp-cuda"

LLAMA_TAG="b9704"
LLAMA_BUILD_NUMBER="9704"
LLAMA_COMMIT="10786217e9d40c848ac0133cbe9c5f22a52421bb"
LLAMA_REPOSITORY="https://github.com/ggml-org/llama.cpp.git"
CUDA_ROOT="/usr/local/cuda-13.3"
CUDA_ARCHITECTURE="86"

jarvis_root="$DEFAULT_JARVIS_ROOT"
dev_root="$DEFAULT_DEV_ROOT"
transcript_path=""
install_build_prereqs=false
keep_previous_runtime=false

usage() {
    cat <<'USAGE'
Usage: docs/jarvis-wsl-llamacpp.sh [options]

Options:
  --jarvis-root PATH       JARVIS repository root.
  --dev-root PATH          External build workspace.
                           Default: ~/WORK/CODE/jarvis-dev/llamacpp-cuda
  --transcript PATH        Build transcript path.
  --install-build-prereqs  Install missing generic Ubuntu build tools with sudo.
  --keep-previous-runtime  Retain the replaced runtime under the external workspace.
  -h, --help               Show this help.

The helper never installs or changes NVIDIA drivers or CUDA packages.
USAGE
}

log() { printf '\n==> %s\n' "$*"; }
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
run() { printf '+'; printf ' %q' "$@"; printf '\n'; "$@"; }
has() { command -v "$1" >/dev/null 2>&1; }
cache_value() {
    local key="$1" cache="$2"
    awk -F= -v key="$key" '$1 ~ ("^" key ":[^=]+$") { print substr($0, index($0, "=") + 1); exit }' "$cache"
}
probe() {
    local label="$1"
    shift
    local output status
    set +e
    output="$("$@" 2>&1)"
    status=$?
    set -e
    printf '%s\n' "$output"
    ((status == 0)) || die "$label failed with exit code $status"
    PROBE_OUTPUT="$output"
}

while (($#)); do
    case "$1" in
        --jarvis-root) (($# >= 2)) || die "--jarvis-root requires a path"; jarvis_root="$2"; shift 2 ;;
        --dev-root) (($# >= 2)) || die "--dev-root requires a path"; dev_root="$2"; shift 2 ;;
        --transcript) (($# >= 2)) || die "--transcript requires a path"; transcript_path="$2"; shift 2 ;;
        --install-build-prereqs) install_build_prereqs=true; shift ;;
        --keep-previous-runtime) keep_previous_runtime=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) die "Unknown option: $1" ;;
    esac
done

[[ "$(uname -s)" == "Linux" ]] || die "This helper supports Linux/WSL only"
[[ "$(uname -m)" == "x86_64" ]] || die "This helper supports Linux AMD64 only"
[[ -d "$jarvis_root" ]] || die "JARVIS root does not exist: $jarvis_root"
jarvis_root="$(cd -- "$jarvis_root" && pwd)"
[[ -f "$jarvis_root/config/models/llm.yaml" ]] || die "Not a JARVIS repository: $jarvis_root"

mkdir -p -- "$dev_root"
dev_root="$(cd -- "$dev_root" && pwd)"
if [[ -z "$transcript_path" ]]; then
    transcript_path="$dev_root/$(date +%Y%m%d%H%M%S)_jarvis-wsl-llamacpp-transcript.log"
fi
mkdir -p -- "$(dirname -- "$transcript_path")"
exec > >(tee -a "$transcript_path") 2>&1

missing_packages=()
has git || missing_packages+=(git)
has cmake || missing_packages+=(cmake)
has ninja || missing_packages+=(ninja-build)
has gcc || missing_packages+=(build-essential)
has g++ || missing_packages+=(build-essential)
has readelf || missing_packages+=(binutils)
has ldd || missing_packages+=(libc-bin)
has flock || missing_packages+=(util-linux)
if ((${#missing_packages[@]})); then
    mapfile -t missing_packages < <(printf '%s\n' "${missing_packages[@]}" | awk '!seen[$0]++')
    [[ "$install_build_prereqs" == true ]] || die "Missing build prerequisites: ${missing_packages[*]}. Re-run with --install-build-prereqs."
    run sudo apt-get update
    run sudo apt-get install --yes "${missing_packages[@]}"
fi

CUDA_COMPILER="$CUDA_ROOT/bin/nvcc"
[[ -x "$CUDA_COMPILER" ]] || die "CUDA compiler unavailable: $CUDA_COMPILER"
[[ -d "$CUDA_ROOT/include" ]] || die "CUDA headers unavailable: $CUDA_ROOT/include"
[[ -d "$CUDA_ROOT/lib64" ]] || die "CUDA libraries unavailable: $CUDA_ROOT/lib64"

export PATH="$CUDA_ROOT/bin${PATH:+:$PATH}"
export LD_LIBRARY_PATH="$CUDA_ROOT/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export CUDA_HOME="$CUDA_ROOT"
export CUDACXX="$CUDA_COMPILER"

source_root="$dev_root/llama.cpp"
build_key="${LLAMA_TAG}-${LLAMA_COMMIT:0:12}-cuda13.3-sm${CUDA_ARCHITECTURE}-upstream-rpath"
build_root="$dev_root/build/$build_key"
fingerprint_path="$build_root/.jarvis-build-fingerprint"
lock_path="$dev_root/.build.lock"
runtime_root="$jarvis_root/runtimes/llama.cpp/linux-amd64-cuda"
runtime_parent="$(dirname -- "$runtime_root")"
runtime_stage="$runtime_parent/linux-amd64-cuda.stage.$$"
failed_stage="$dev_root/failed-stage-$(date +%Y%m%d%H%M%S)"
previous_runtime="$dev_root/previous-runtime-$(date +%Y%m%d%H%M%S)"
stage_installed=false

cleanup() {
    local status=$?
    if [[ "$stage_installed" != true && -d "$runtime_stage" ]]; then
        mv -- "$runtime_stage" "$failed_stage"
        printf 'Failed stage preserved at: %s\n' "$failed_stage" >&2
    fi
    exit "$status"
}
trap cleanup EXIT

exec 9>"$lock_path"
flock -n 9 || die "Another llama.cpp CUDA build is already using: $dev_root"

log "Build inputs"
printf 'JARVIS root: %s\n' "$jarvis_root"
printf 'Developer workspace: %s\n' "$dev_root"
printf 'Transcript: %s\n' "$transcript_path"
printf 'llama.cpp: %s (%s)\n' "$LLAMA_TAG" "$LLAMA_COMMIT"
printf 'CUDA toolkit: %s\n' "$CUDA_ROOT"
printf 'CUDA architecture: %s\n' "$CUDA_ARCHITECTURE"
printf 'Build workspace: %s\n' "$build_root"

log "Verify Linux/WSL NVIDIA CUDA prerequisites"
run nvidia-smi
run "$CUDA_COMPILER" --version
run gcc --version
run g++ --version
run cmake --version
run ninja --version

log "Clone or update pinned llama.cpp source"
if [[ ! -d "$source_root/.git" ]]; then
    [[ ! -e "$source_root" ]] || die "Existing source path is not a Git checkout: $source_root"
    run git clone --filter=blob:none --no-checkout "$LLAMA_REPOSITORY" "$source_root"
fi
run git -C "$source_root" remote set-url origin "$LLAMA_REPOSITORY"
run git -C "$source_root" fetch --force --tags origin "refs/tags/$LLAMA_TAG:refs/tags/$LLAMA_TAG"
resolved_commit="$(git -C "$source_root" rev-parse "refs/tags/$LLAMA_TAG^{commit}")"
[[ "$resolved_commit" == "$LLAMA_COMMIT" ]] || die "Tag $LLAMA_TAG resolved to $resolved_commit, expected $LLAMA_COMMIT"
run git -C "$source_root" checkout --detach --force "$LLAMA_COMMIT"
[[ -z "$(git -C "$source_root" status --porcelain --untracked-files=no)" ]] || die "Pinned source checkout is modified"
resolved_build_number="$(git -C "$source_root" rev-list --count HEAD)"
[[ "$resolved_build_number" == "$LLAMA_BUILD_NUMBER" ]] || die "Pinned checkout reports build $resolved_build_number, expected $LLAMA_BUILD_NUMBER"

fingerprint="$(cat <<EOF
llama_tag=$LLAMA_TAG
llama_commit=$LLAMA_COMMIT
llama_build_number_source=git
cuda_root=$CUDA_ROOT
cuda_compiler=$(readlink -f "$CUDA_COMPILER")
nvcc=$($CUDA_COMPILER --version | tail -n 1)
cuda_architecture=$CUDA_ARCHITECTURE
host_compiler=$(readlink -f "$(command -v gcc)")
host_compiler_version=$(gcc -dumpfullversion -dumpversion)
cmake=$(cmake --version | head -n 1)
generator=Ninja
build_type=Release
shared_libraries=ON
build_with_install_rpath=ON
install_rpath=$CUDA_ROOT/lib64;\$ORIGIN
EOF
)"
if [[ -d "$build_root" ]]; then
    recorded_fingerprint=""
    [[ -f "$fingerprint_path" ]] && recorded_fingerprint="$(cat "$fingerprint_path")"
    if [[ "$recorded_fingerprint" != "$fingerprint" ]]; then
        log "Discard incompatible build tree"
        rm -rf -- "$build_root"
    fi
fi
mkdir -p -- "$build_root"
printf '%s\n' "$fingerprint" > "$fingerprint_path"

log "Configure pinned CUDA Release build"
run cmake -S "$source_root" -B "$build_root" -G Ninja \
    -DGGML_CUDA=ON \
    -DGGML_NATIVE=OFF \
    -DBUILD_SHARED_LIBS=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_COMPILER="$CUDA_COMPILER" \
    -DCUDAToolkit_ROOT="$CUDA_ROOT" \
    -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCHITECTURE" \
    -DCMAKE_BUILD_WITH_INSTALL_RPATH=ON \
    "-DCMAKE_INSTALL_RPATH=$CUDA_ROOT/lib64;\$ORIGIN" \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_TOOLS=ON \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_SERVER=ON \
    -DLLAMA_BUILD_APP=OFF \
    -DLLAMA_BUILD_UI=OFF \
    -DLLAMA_USE_PREBUILT_UI=OFF

log "Verify configured CUDA backend"
cache="$build_root/CMakeCache.txt"
[[ -f "$cache" ]] || die "CMake cache was not created: $cache"
[[ "$(cache_value GGML_CUDA "$cache")" == "ON" ]] || die "CMake did not enable GGML_CUDA"
configured_cuda_compiler="$(cache_value CMAKE_CUDA_COMPILER "$cache")"
[[ -n "$configured_cuda_compiler" ]] || die "CMake cache does not record a CUDA compiler"
[[ "$(readlink -f "$configured_cuda_compiler")" == "$(readlink -f "$CUDA_COMPILER")" ]] || die "CMake selected CUDA compiler '$configured_cuda_compiler', expected '$CUDA_COMPILER'"
[[ "$(cache_value CMAKE_CUDA_ARCHITECTURES "$cache")" == "$CUDA_ARCHITECTURE" ]] || die "CMake selected an unexpected CUDA architecture"
[[ "$(cache_value CMAKE_BUILD_WITH_INSTALL_RPATH "$cache")" == "ON" ]] || die "CMake did not enable install RPATH for the build tree"
printf 'Configured CUDA compiler: %s\n' "$configured_cuda_compiler"
printf 'Configured CUDA architecture: %s\n' "$(cache_value CMAKE_CUDA_ARCHITECTURES "$cache")"

log "Build llama-server"
run cmake --build "$build_root" --target llama-server --parallel "$(nproc)"

build_bin="$build_root/bin"
[[ -x "$build_bin/llama-server" ]] || die "Build produced no executable: $build_bin/llama-server"

log "Remove abandoned JARVIS staging directories"
mkdir -p -- "$runtime_parent"
find "$runtime_parent" -maxdepth 1 -mindepth 1 -type d -name 'linux-amd64-cuda.stage.*' -print -exec rm -rf -- {} +

log "Stage executable and adjacent shared libraries"
mkdir -p -- "$runtime_stage"
cp -a -- "$build_bin/llama-server" "$runtime_stage/"
while IFS= read -r -d '' artifact; do
    cp -a -- "$artifact" "$runtime_stage/"
done < <(find "$build_bin" -maxdepth 1 \( -type f -o -type l \) \( -name '*.so' -o -name '*.so.*' \) -print0)

required_files=(llama-server libllama-server-impl.so libllama-common.so.0 libggml.so libggml-base.so libggml-cpu.so libggml-cuda.so libllama.so libmtmd.so)
for required in "${required_files[@]}"; do
    [[ -e "$runtime_stage/$required" ]] || die "Required staged file missing: $required"
done

log "Verify staged provenance, linkage, and CUDA device discovery"
probe "Staged llama-server --version" "$runtime_stage/llama-server" --version
version_output="$PROBE_OUTPUT"
grep -Fq "$LLAMA_BUILD_NUMBER" <<<"$version_output" || die "Staged llama-server does not report build $LLAMA_BUILD_NUMBER"
grep -Fq "${LLAMA_COMMIT:0:8}" <<<"$version_output" || die "Staged llama-server does not report pinned commit $LLAMA_COMMIT"
for library in libllama.so.0.0."$LLAMA_BUILD_NUMBER" libllama-common.so.0.0."$LLAMA_BUILD_NUMBER" libmtmd.so.0.0."$LLAMA_BUILD_NUMBER"; do
    [[ -e "$runtime_stage/$library" ]] || die "Expected versioned library missing: $library"
done

readelf_output="$(readelf -d "$runtime_stage/llama-server")"
printf '%s\n' "$readelf_output"
grep -Eq "Library (rpath|runpath): \[[^]]*$CUDA_ROOT/lib64[^]]*\$ORIGIN[^]]*\]" <<<"$readelf_output" || die "Staged llama-server RUNPATH does not contain CUDA 13.3 and \$ORIGIN"
ldd_output="$(ldd "$runtime_stage/llama-server")"
printf '%s\n' "$ldd_output"
grep -Fq 'not found' <<<"$ldd_output" && die "Staged runtime has unresolved shared libraries"
grep -Fq "$build_root" <<<"$ldd_output" && die "Staged runtime still resolves libraries from the build tree"
while IFS= read -r line; do
    [[ "$line" =~ ^[[:space:]]*(libggml|libllama|libmtmd) ]] || continue
    resolved="$(awk '{print $3}' <<<"$line")"
    [[ "$resolved" == "$runtime_stage/"* ]] || die "llama.cpp library resolved outside staging: $line"
done <<<"$ldd_output"
grep -Eq 'libcudart\.so\.13 => /usr/local/cuda-13\.3/' <<<"$ldd_output" || die "CUDA runtime did not resolve from CUDA 13.3"
grep -Eq 'libcublas(Lt)?\.so\.13 => /usr/local/cuda-13\.3/' <<<"$ldd_output" || die "cuBLAS did not resolve from CUDA 13.3"
grep -Eq 'libcuda\.so\.1 => /usr/lib/wsl/lib/libcuda\.so\.1' <<<"$ldd_output" || die "NVIDIA driver library did not resolve from WSL"

probe "Staged llama-server --list-devices" "$runtime_stage/llama-server" --list-devices
devices_output="$PROBE_OUTPUT"
grep -Eiq 'CUDA|NVIDIA GeForce RTX 3060' <<<"$devices_output" || die "Staged llama-server did not enumerate the NVIDIA CUDA device"

log "Atomically replace JARVIS CUDA runtime"
if [[ -d "$runtime_root" ]]; then
    mv -- "$runtime_root" "$previous_runtime"
fi
if ! mv -- "$runtime_stage" "$runtime_root"; then
    [[ -d "$previous_runtime" ]] && mv -- "$previous_runtime" "$runtime_root"
    die "Unable to install staged runtime"
fi
stage_installed=true
if [[ -d "$previous_runtime" && "$keep_previous_runtime" != true ]]; then
    rm -rf -- "$previous_runtime"
fi

log "Verify installed managed runtime"
run "$jarvis_root/backend/.venv/bin/python" "$jarvis_root/scripts/ensure_models.py" --family llm --verify-only
installed_ldd="$(ldd "$runtime_root/llama-server")"
printf '%s\n' "$installed_ldd"
grep -Fq 'not found' <<<"$installed_ldd" && die "Installed runtime has unresolved shared libraries"
grep -Fq "$build_root" <<<"$installed_ldd" && die "Installed runtime resolves libraries from the external build tree"

printf '\nPASS: Linux AMD64/WSL2 CUDA llama.cpp runtime staged at %s\n' "$runtime_root"
printf 'Transcript: %s\n' "$transcript_path"
printf 'Pinned source: %s (%s)\n' "$LLAMA_TAG" "$LLAMA_COMMIT"
printf 'Build workspace: %s\n' "$build_root"
printf 'Next validation: backend/.venv/bin/python scripts/validate_backend.py runtime --families llm --devices cuda\n'
