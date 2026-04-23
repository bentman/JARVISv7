from __future__ import annotations

import subprocess


def _run_command(command: list[str]) -> str:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        return ""
    return (completed.stdout or completed.stderr or "").strip()


def detect_cuda_info() -> dict[str, str | bool | None]:
    try:
        nvidia_smi_output = _run_command(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"]
        )
    except (FileNotFoundError, OSError):
        nvidia_smi_output = ""

    if nvidia_smi_output:
        driver_version = nvidia_smi_output.splitlines()[0].strip()
        return {
            "cuda_available": True,
            "cuda_version": driver_version or None,
        }

    try:
        nvcc_output = _run_command(["nvcc", "--version"])
    except (FileNotFoundError, OSError):
        nvcc_output = ""

    if nvcc_output:
        version_line = next(
            (line.strip() for line in nvcc_output.splitlines() if "release" in line.lower()),
            None,
        )
        return {
            "cuda_available": True,
            "cuda_version": version_line,
        }

    return {
        "cuda_available": False,
        "cuda_version": None,
    }
