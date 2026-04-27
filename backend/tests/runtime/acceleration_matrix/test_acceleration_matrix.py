from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from backend.app.core.capabilities import HardwareProfile
from backend.app.core.paths import REPO_ROOT
from backend.app.hardware.preflight import PreflightResult
from backend.app.runtimes.stt.onnx_whisper_runtime import OnnxWhisperRuntime
from backend.tests.conftest import SKIP_UNLESS_LIVE


ALLOWED_STATE_PREFIXES = ("PASS", "SKIP-", "PENDING-H.2", "N/A", "BLOCKED-")
REPORT_PATH = REPO_ROOT / "reports" / "validation" / "b5-acceleration-matrix-current-host.txt"


@dataclass(frozen=True)
class MatrixCell:
    family: str
    device: str
    state: str
    evidence: str


def _has_token(preflight: PreflightResult, token: str) -> bool:
    return token in preflight.tokens


def _state_allowed(state: str) -> bool:
    return any(state == prefix or state.startswith(prefix) for prefix in ALLOWED_STATE_PREFIXES)


def _cpu_import_state(preflight: PreflightResult, import_token: str) -> str:
    if _has_token(preflight, import_token):
        return "PASS"
    return f"BLOCKED-{import_token}-missing"


def _cuda_state(preflight: PreflightResult) -> str:
    if _has_token(preflight, "ep:CUDAExecutionProvider"):
        return "PASS"
    return "SKIP-no-cuda-ep"


def _directml_state(preflight: PreflightResult) -> str:
    if _has_token(preflight, "ep:DmlExecutionProvider"):
        return "PASS"
    return "SKIP-no-directml-ep"


def _ollama_state() -> str:
    if not os.getenv("JARVISV7_OLLAMA_URL", "").strip():
        return "SKIP-no-ollama"
    return "PASS"


def _assert_stt_qnn_defers_to_h2() -> None:
    runtime = OnnxWhisperRuntime(device="qnn")
    with pytest.raises(NotImplementedError, match=r"H\.2"):
        runtime.transcribe(np.array([], dtype=np.float32), sample_rate=16000)


def _matrix_for_current_host(profile: HardwareProfile, preflight: PreflightResult) -> list[MatrixCell]:
    arch_evidence = f"arch={profile.arch}"
    return [
        MatrixCell("stt", "cpu", _cpu_import_state(preflight, "import:onnxruntime"), "import:onnxruntime"),
        MatrixCell("stt", "cuda", _cuda_state(preflight), "ep:CUDAExecutionProvider"),
        MatrixCell("stt", "directml", _directml_state(preflight), "ep:DmlExecutionProvider"),
        MatrixCell("stt", "qnn", "PENDING-H.2", "OnnxWhisperRuntime qnn defers to H.2"),
        MatrixCell("tts", "cpu", _cpu_import_state(preflight, "import:kokoro_onnx"), "import:kokoro_onnx"),
        MatrixCell("tts", "cuda", _cuda_state(preflight), "ep:CUDAExecutionProvider"),
        MatrixCell("tts", "directml", _directml_state(preflight), "ep:DmlExecutionProvider"),
        MatrixCell("tts", "qnn", "N/A", "no QNN TTS in Slice B"),
        MatrixCell("llm", "ollama/local", _ollama_state(), "JARVISV7_OLLAMA_URL env gate"),
        MatrixCell("llm", "cuda", "N/A", "LLM device is runtime, not EP"),
        MatrixCell("llm", "directml", "N/A", "LLM device is runtime, not EP"),
        MatrixCell("llm", "qnn", "N/A", "LLM device is runtime, not EP"),
        MatrixCell("wake", "cpu", _cpu_import_state(preflight, "import:openwakeword"), "import:openwakeword"),
        MatrixCell("wake", "cuda", "N/A", "wake is CPU-only"),
        MatrixCell("wake", "directml", "N/A", "wake is CPU-only"),
        MatrixCell("wake", "qnn", "N/A", "wake is CPU-only"),
        MatrixCell("host", "class", "PASS", arch_evidence),
    ]


def _format_matrix(cells: list[MatrixCell]) -> str:
    lines = ["family,device,state,evidence"]
    lines.extend(f"{cell.family},{cell.device},{cell.state},{cell.evidence}" for cell in cells)
    return "\n".join(lines) + "\n"


@pytest.mark.live
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_b5_known_state_acceleration_matrix_current_host(profiler_fixture, preflight_fixture):
    profile = profiler_fixture.profile

    _assert_stt_qnn_defers_to_h2()
    cells = _matrix_for_current_host(profile, preflight_fixture)
    matrix = _format_matrix(cells)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(matrix, encoding="utf-8")

    invalid_states = [cell for cell in cells if not _state_allowed(cell.state)]
    blocked_cells = [cell for cell in cells if cell.state.startswith("BLOCKED-")]

    assert not invalid_states, matrix
    assert not blocked_cells, matrix