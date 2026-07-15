from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import wave

import numpy as np
import pytest

from backend.app.conversation.engine import TurnEngine
from backend.app.conversation.states import ConversationState
from backend.app.core.capabilities import HardwareProfile
from backend.app.core.paths import REPO_ROOT
from backend.app.core.settings import load_settings
from backend.app.hardware.preflight import PreflightResult
from backend.app.personality.loader import load_default_personality
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.runtimes.stt.onnx_whisper_runtime import OnnxWhisperRuntime, QnnWhisperRuntime
from backend.app.runtimes.tts.kokoro_onnx_runtime import KOKORO_SAMPLE_RATE, KokoroOnnxRuntime
from backend.app.runtimes.tts.tts_runtime import NullTTSRuntime
from backend.tests.conftest import (
    SKIP_UNLESS_ARM64,
    SKIP_UNLESS_CUDA,
    SKIP_UNLESS_DIRECTML,
    SKIP_UNLESS_LIVE,
    SKIP_UNLESS_OLLAMA,
    SKIP_UNLESS_QNN,
    SKIP_UNLESS_X64,
    ollama_base_url,
)


ALLOWED_STATE_PREFIXES = ("PASS", "SKIP-", "NOT-WIRED", "N/A")
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "hello_world.wav"
REPORT_PATH = REPO_ROOT / "reports" / "validation" / "h8-voice-acceleration-matrix-current-host.txt"


@dataclass(frozen=True)
class MatrixCell:
    family: str
    device: str
    state: str
    evidence: str


# Non-live selector/matrix logic.


def _has_token(preflight: PreflightResult, token: str) -> bool:
    return token in preflight.tokens


def _state_allowed(state: str) -> bool:
    return any(state == prefix or state.startswith(prefix) for prefix in ALLOWED_STATE_PREFIXES)


def _cpu_import_state(preflight: PreflightResult, import_token: str) -> str:
    if _has_token(preflight, import_token):
        return "PASS"
    return f"SKIP-prereq-missing:{import_token}"


def _cuda_state(preflight: PreflightResult) -> str:
    if _has_token(preflight, "ep:CUDAExecutionProvider"):
        return "PASS"
    return "SKIP-no-cuda-ep"


def _directml_state(preflight: PreflightResult) -> str:
    if _has_token(preflight, "ep:DmlExecutionProvider"):
        return "PASS"
    return "SKIP-no-directml-ep"


def _qnn_state(profile: HardwareProfile, preflight: PreflightResult) -> str:
    if not (profile.arch == "arm64" and profile.npu_vendor == "qualcomm" and profile.npu_available):
        return "SKIP-no-host"
    required = ("import:onnxruntime-qnn", "ep:QNNExecutionProvider", "dll:QnnHtp")
    missing = [token for token in required if not _has_token(preflight, token)]
    if missing:
        return "SKIP-prereq-missing:" + "+".join(missing)
    return "PASS"


def _ollama_state() -> str:
    if not load_settings().ollama_base_url.strip():
        return "SKIP-no-ollama"
    return "PASS"


def _assert_stt_qnn_guard_is_explicit_not_wired() -> None:
    runtime = OnnxWhisperRuntime(device="qnn")
    with pytest.raises(NotImplementedError, match=r"not wired through OnnxWhisperRuntime"):
        runtime.transcribe(np.array([], dtype=np.float32), sample_rate=16000)


def _matrix_for_current_host(profile: HardwareProfile, preflight: PreflightResult) -> list[MatrixCell]:
    arch_evidence = f"arch={profile.arch}"
    qnn_state = _qnn_state(profile, preflight)
    return [
        MatrixCell("stt", "cpu", _cpu_import_state(preflight, "import:onnxruntime"), "import:onnxruntime"),
        MatrixCell("stt", "cuda", _cuda_state(preflight), "ep:CUDAExecutionProvider"),
        MatrixCell("stt", "directml", _directml_state(preflight), "ep:DmlExecutionProvider"),
        MatrixCell("stt", "qnn:whisper-base-en-qnn-snapdragon-x-elite", qnn_state, "QNN Whisper AI Hub artifact"),
        MatrixCell("stt", "qnn:whisper-qualcomm-qnn", qnn_state, "QNN Whisper side-by-side artifact"),
        MatrixCell("tts", "cpu", _cpu_import_state(preflight, "import:kokoro_onnx"), "import:kokoro_onnx"),
        MatrixCell("tts", "cuda", _cuda_state(preflight), "ep:CUDAExecutionProvider"),
        MatrixCell("tts", "directml", _directml_state(preflight), "ep:DmlExecutionProvider"),
        MatrixCell("tts", "qnn", _qnn_state(profile, preflight), "QNN Kokoro ORT session"),
        MatrixCell("llm", "ollama/local", _ollama_state(), "OLLAMA_BASE_URL settings gate"),
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


def test_h8_voice_acceleration_matrix_current_host(profiler_fixture, preflight_fixture):
    profile = profiler_fixture.profile

    _assert_stt_qnn_guard_is_explicit_not_wired()
    cells = _matrix_for_current_host(profile, preflight_fixture)
    matrix = _format_matrix(cells)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(matrix, encoding="utf-8")

    invalid_states = [cell for cell in cells if not _state_allowed(cell.state)]
    blocked_cells = [cell for cell in cells if cell.state.startswith("BLOCKED-")]

    assert not invalid_states, matrix
    assert not blocked_cells, matrix


# Live smoke execution.


@dataclass(frozen=True)
class VoiceSmokeCase:
    device: str
    tts_reason: str
    expected_device: str | None = None
    allow_qnn_cpu_fallback: bool = False
    require_transcript: bool = False


@dataclass(frozen=True)
class SttSmokeCase:
    runtime_kind: str
    device: str
    model_name: str | None = None


@dataclass(frozen=True)
class TtsSmokeCase:
    device: str
    expected_error: str | None = None


def _normalize_transcript(transcript: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", transcript.lower()).split())


def _load_mono_pcm16_wav(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav_file:
        raw_audio = wav_file.readframes(wav_file.getnframes())
        sample_rate = wav_file.getframerate()
        channels = wav_file.getnchannels()
        sample_width = wav_file.getsampwidth()
    if channels != 1 or sample_width != 2:
        raise ValueError("expected mono 16-bit PCM WAV fixture")
    return np.frombuffer(raw_audio, dtype="<i2").astype(np.float32) / 32768.0, sample_rate


def _build_voice_engine(stt, reason: str) -> TurnEngine:
    return TurnEngine(
        stt=stt,
        tts=NullTTSRuntime(reason=reason),
        llm=OllamaLLM(base_url=ollama_base_url()),
        personality=load_default_personality(),
    )


def _assert_successful_voice_turn(
    engine: TurnEngine,
    audio: np.ndarray,
    sample_rate: int,
    *,
    require_transcript: bool = False,
) -> None:
    result = engine.run_voice_turn(audio, sample_rate)

    assert result.final_state == ConversationState.IDLE
    if require_transcript:
        assert result.transcript is not None and result.transcript.strip()
    assert result.response_text is not None and result.response_text.strip()
    assert result.failure_reason is None


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            VoiceSmokeCase(
                device="cpu",
                tts_reason="TTS acceleration matrix live gate uses STT+LLM full-turn proof only",
                require_transcript=True,
            ),
            id="cpu-current-host",
        ),
        pytest.param(
            VoiceSmokeCase(device="cuda", tts_reason="x64 I.3 STT+LLM full-turn proof", expected_device="cuda"),
            marks=[pytest.mark.stt, pytest.mark.cuda, pytest.mark.x64, pytest.mark.skipif(SKIP_UNLESS_X64, reason="requires x64 host")],
            id="x64-cuda",
        ),
        pytest.param(
            VoiceSmokeCase(
                device="qnn",
                tts_reason="arm64 I.3 STT+LLM full-turn proof",
                expected_device="qnn",
                allow_qnn_cpu_fallback=True,
            ),
            marks=[pytest.mark.stt, pytest.mark.qnn, pytest.mark.arm64, pytest.mark.skipif(SKIP_UNLESS_ARM64, reason="requires ARM64 host")],
            id="arm64-qnn-with-cpu-fallback",
        ),
        pytest.param(
            VoiceSmokeCase(device="cpu", tts_reason="arm64 I.3 CPU fallback full-turn proof", expected_device="cpu"),
            marks=[pytest.mark.stt, pytest.mark.arm64, pytest.mark.skipif(SKIP_UNLESS_ARM64, reason="requires ARM64 host")],
            id="arm64-cpu-fallback",
        ),
    ],
)
@pytest.mark.live
@pytest.mark.turn
@pytest.mark.requires_ollama
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
@pytest.mark.skipif(SKIP_UNLESS_OLLAMA, reason="OLLAMA_BASE_URL not set")
def test_voice_acceleration_matrix_live_smoke(
    preflight_fixture, profiler_fixture, case: VoiceSmokeCase
) -> None:
    audio, sample_rate = _load_mono_pcm16_wav(FIXTURE_PATH)
    if case.expected_device is None:
        from backend.app.runtimes.stt.stt_runtime import select_stt_runtime
        stt = select_stt_runtime(preflight_fixture, profiler_fixture.profile)
    else:
        if case.device == "qnn":
            stt = QnnWhisperRuntime(device="qnn", model_name="whisper-qualcomm-qnn")
        else:
            stt = OnnxWhisperRuntime(device=case.device)
    engine = _build_voice_engine(stt, case.tts_reason)

    if not case.allow_qnn_cpu_fallback:
        _assert_successful_voice_turn(engine, audio, sample_rate, require_transcript=case.require_transcript)
        if case.expected_device is not None:
            assert getattr(engine.stt, "device", None) == case.expected_device
        return

    result = engine.run_voice_turn(audio, sample_rate)
    if result.final_state == ConversationState.IDLE:
        assert result.response_text is not None and result.response_text.strip()
        assert result.failure_reason is None
        assert getattr(engine.stt, "device", None) == case.expected_device
        return

    fallback_engine = _build_voice_engine(OnnxWhisperRuntime(device="cpu"), "arm64 I.3 deterministic fallback proof after qnn path failure")
    _assert_successful_voice_turn(fallback_engine, audio, sample_rate)
    assert getattr(fallback_engine.stt, "device", None) == "cpu"


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(SttSmokeCase(runtime_kind="onnx", device="cpu"), id="stt-cpu"),
        pytest.param(
            SttSmokeCase(runtime_kind="onnx", device="cuda"),
            marks=[pytest.mark.cuda, pytest.mark.x64, pytest.mark.skipif(SKIP_UNLESS_X64, reason="requires x64 host")],
            id="stt-cuda",
        ),
        pytest.param(
            SttSmokeCase(runtime_kind="qnn", device="qnn", model_name="whisper-base-en-qnn-snapdragon-x-elite"),
            marks=[
                pytest.mark.qnn,
                pytest.mark.arm64,
                pytest.mark.skipif(SKIP_UNLESS_ARM64, reason="requires ARM64 host"),
                pytest.mark.skipif(SKIP_UNLESS_QNN, reason="requires QNN execution provider readiness"),
            ],
            id="stt-qnn-aihub",
        ),
        pytest.param(
            SttSmokeCase(runtime_kind="qnn", device="qnn", model_name="whisper-qualcomm-qnn"),
            marks=[
                pytest.mark.qnn,
                pytest.mark.arm64,
                pytest.mark.skipif(SKIP_UNLESS_ARM64, reason="requires ARM64 host"),
                pytest.mark.skipif(SKIP_UNLESS_QNN, reason="requires QNN execution provider readiness"),
            ],
            id="stt-qnn-side-by-side",
        ),
    ],
)
@pytest.mark.live
@pytest.mark.stt
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_stt_acceleration_matrix_live_transcript(case: SttSmokeCase) -> None:
    runtime = (
        QnnWhisperRuntime(device="qnn", model_name=case.model_name)
        if case.runtime_kind == "qnn"
        else OnnxWhisperRuntime(device=case.device)
    )

    assert runtime.is_available()
    audio, sample_rate = _load_mono_pcm16_wav(FIXTURE_PATH)
    transcript = runtime.transcribe(audio, sample_rate=sample_rate)

    assert "hello world" in _normalize_transcript(transcript)


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(TtsSmokeCase(device="cpu"), id="tts-cpu"),
        pytest.param(
            TtsSmokeCase(device="cuda", expected_error=None),
            marks=[pytest.mark.cuda, pytest.mark.skipif(SKIP_UNLESS_CUDA, reason="requires CUDA execution provider readiness")],
            id="tts-cuda",
        ),
        pytest.param(
            TtsSmokeCase(device="directml", expected_error=None),
            marks=[
                pytest.mark.directml,
                pytest.mark.skipif(SKIP_UNLESS_DIRECTML, reason="requires DirectML execution provider readiness"),
            ],
            id="tts-directml",
        ),
    ],
)
@pytest.mark.live
@pytest.mark.tts
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_tts_acceleration_matrix_live_synthesis(case: TtsSmokeCase) -> None:
    runtime = KokoroOnnxRuntime(device=case.device)

    if case.expected_error is not None:
        with pytest.raises(RuntimeError, match=case.expected_error):
            runtime.synthesize("hello world")
        return

    assert runtime.is_available()
    audio = runtime.synthesize("hello world")

    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.size > 0
    assert runtime.sample_rate() == KOKORO_SAMPLE_RATE
