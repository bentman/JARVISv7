from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

from backend.app.conversation.engine import TurnResult
from backend.app.conversation.states import ConversationState
from backend.app.core.capabilities import CapabilityFlags, HardwareProfile
from backend.app.hardware.preflight import PreflightResult
from scripts import run_jarvis


@dataclass(slots=True)
class _Report:
    profile: HardwareProfile
    flags: CapabilityFlags


class _FakeLLM:
    reason = "available"

    def is_available(self) -> bool:
        return True


class _UnavailableLLM:
    reason = "ollama unavailable: connection refused"

    def is_available(self) -> bool:
        return False


class _FakeEngine:
    def __init__(self, llm=None) -> None:
        self.llm = llm or _FakeLLM()


def _fake_report() -> _Report:
    return _Report(
        profile=HardwareProfile(
            arch="amd64",
            os_name="windows",
            profile_id="profile-test",
            profiled_at="2026-04-27T00:00:00Z",
        ),
        flags=CapabilityFlags(
            supports_local_stt=True,
            supports_local_tts=True,
            supports_local_llm=True,
            supports_wake_word=True,
        ),
    )


def _fake_preflight() -> PreflightResult:
    return PreflightResult(
        tokens=["import:onnxruntime", "import:kokoro_onnx", "import:openwakeword"],
        dll_discovery_log=[],
        probe_errors={},
    )


def _fake_result(turn_id: str = "turn-1") -> TurnResult:
    return TurnResult(
        turn_id=turn_id,
        session_id="session-1",
        transcript="hello",
        response_text="ready",
        final_state=ConversationState.IDLE,
    )


def _patch_startup(monkeypatch, *, stt_ready: bool = True) -> None:
    report = _fake_report()
    monkeypatch.setattr(
        run_jarvis,
        "load_startup_context",
        lambda: SimpleNamespace(
            report=report,
            profile=report.profile,
            extras=["dev"],
            preflight=_fake_preflight(),
            readiness={
                "stt": ("cpu", stt_ready, "stt reason"),
                "tts": ("cpu", True, "tts reason"),
                "llm": ("cpu", True, "llm reason"),
                "wake": ("cpu", True, "wake reason"),
            },
        ),
    )


def test_dry_run_prints_fingerprint_first_and_startup_plan_exits_zero(monkeypatch, capsys) -> None:
    _patch_startup(monkeypatch)
    calls = []
    monkeypatch.setattr(run_jarvis.turn_service, "run_text_turn", lambda *args, **kwargs: calls.append(True))

    exit_code = run_jarvis.main(["--dry-run"])
    output = capsys.readouterr().out.splitlines()

    assert exit_code == 0
    assert output[0].startswith("[fingerprint]")
    assert "JARVISv7 proving host startup" in output[1]
    assert any("readiness stt" in line for line in output)
    assert calls == []


def test_profile_prints_fingerprint_first_and_readiness_summary_exits_zero(monkeypatch, capsys) -> None:
    _patch_startup(monkeypatch)

    exit_code = run_jarvis.main(["--profile"])
    output = capsys.readouterr().out.splitlines()

    assert exit_code == 0
    assert output[0].startswith("[fingerprint]")
    assert any("profile_id=profile-test" in line for line in output)
    assert any("preflight tokens=3" in line for line in output)
    assert sum(1 for line in output if line.startswith("readiness ")) == 4


def test_text_only_turns_one_delegates_through_text_service(monkeypatch, capsys) -> None:
    _patch_startup(monkeypatch)
    calls = []
    monkeypatch.setattr(run_jarvis, "_build_engine", lambda context: _FakeEngine())

    def fake_run_text_turn(text, *, engine):
        calls.append((text, engine))
        return _fake_result()

    monkeypatch.setattr(run_jarvis.turn_service, "run_text_turn", fake_run_text_turn)

    exit_code = run_jarvis.main(["--text-only", "--turns", "1"])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert len(calls) == 1
    assert "final_state=IDLE" in output


def test_build_engine_uses_backend_local_llm_preparation_helper(monkeypatch) -> None:
    context = run_jarvis.StartupContext(
        report=_fake_report(),
        profile=_fake_report().profile,
        extras=["dev"],
        preflight=_fake_preflight(),
        readiness={
            "stt": ("cpu", True, "stt ready"),
            "tts": ("cpu", True, "tts ready"),
            "llm": ("cpu", True, "llm ready"),
            "wake": ("cpu", True, "wake ready"),
        },
    )
    prepared_runtime = _FakeLLM()
    selected_runtime = _FakeLLM()
    prepare_calls = []
    selector_calls = []

    class CapturedEngine:
        def __init__(self, *, stt, tts, llm, personality):
            self.stt = stt
            self.tts = tts
            self.llm = llm
            self.personality = personality

    monkeypatch.setattr(run_jarvis, "select_stt_runtime", lambda preflight, profile: object())
    monkeypatch.setattr(run_jarvis, "select_tts_runtime", lambda preflight, profile: object())
    monkeypatch.setattr(run_jarvis, "load_default_personality", lambda: object())
    monkeypatch.setattr(run_jarvis, "TurnEngine", CapturedEngine)

    def fake_prepare(profile, preflight, *, flags):
        prepare_calls.append((profile, preflight, flags))
        return SimpleNamespace(runtime=prepared_runtime, sidecar="sidecar")

    def fake_select(*, local=None, ollama=None):
        selector_calls.append(local)
        return selected_runtime, "trace"

    monkeypatch.setattr(run_jarvis, "prepare_managed_local_llm", fake_prepare)
    monkeypatch.setattr(run_jarvis, "select_llm", fake_select)

    engine = run_jarvis._build_engine(context)

    assert engine.llm is selected_runtime
    assert context.local_llm_sidecar == "sidecar"
    assert context.llm_trace == "trace"
    assert prepare_calls == [(context.profile, context.preflight, context.report.flags)]
    assert selector_calls == [prepared_runtime]
    assert not hasattr(run_jarvis, "_start_local_llm_if_configured")
    assert not hasattr(run_jarvis, "_wait_for_llama_cpp_ready")


def test_text_only_turns_two_executes_two_turns(monkeypatch, capsys) -> None:
    _patch_startup(monkeypatch)
    calls = []
    monkeypatch.setattr(run_jarvis, "_build_engine", lambda context: _FakeEngine())

    def fake_run_text_turn(text, *, engine):
        calls.append(text)
        return _fake_result(f"turn-{len(calls)}")

    monkeypatch.setattr(run_jarvis.turn_service, "run_text_turn", fake_run_text_turn)

    exit_code = run_jarvis.main(["--text-only", "--turns", "2"])
    capsys.readouterr()

    assert exit_code == 0
    assert len(calls) == 2


def test_voice_only_uses_capture_audio_and_voice_service(monkeypatch, capsys) -> None:
    _patch_startup(monkeypatch)
    monkeypatch.setattr(run_jarvis, "_build_engine", lambda context: _FakeEngine())
    monkeypatch.setattr(
        run_jarvis.voice_service,
        "capture_audio",
        lambda duration_s: (np.zeros(160, dtype=np.float32), 16000),
    )
    calls = []

    def fake_run_voice_turn(audio, sample_rate, *, engine):
        calls.append((audio, sample_rate, engine))
        return _fake_result()

    monkeypatch.setattr(run_jarvis.turn_service, "run_voice_turn", fake_run_voice_turn)

    exit_code = run_jarvis.main(["--voice-only"])
    capsys.readouterr()

    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0][1] == 16000


def test_voice_only_reports_audio_device_error_when_capture_raises(monkeypatch, capsys) -> None:
    _patch_startup(monkeypatch)
    monkeypatch.setattr(run_jarvis, "_build_engine", lambda context: _FakeEngine())

    def raise_capture(duration_s):
        raise run_jarvis.voice_service.AudioCaptureError("audio capture failed: unavailable")

    monkeypatch.setattr(run_jarvis.voice_service, "capture_audio", raise_capture)

    exit_code = run_jarvis.main(["--voice-only"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "AUDIO_DEVICE_ERROR audio capture failed: unavailable" in output


def test_stt_unavailable_reports_named_failure(monkeypatch, capsys) -> None:
    _patch_startup(monkeypatch, stt_ready=False)

    exit_code = run_jarvis.main(["--voice-only"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "STT_UNAVAILABLE stt reason" in output


def test_llm_unavailable_reports_named_failure(monkeypatch, capsys) -> None:
    _patch_startup(monkeypatch)
    monkeypatch.setattr(run_jarvis, "_build_engine", lambda context: _FakeEngine(_UnavailableLLM()))

    exit_code = run_jarvis.main(["--text-only"])
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "LLM_UNAVAILABLE ollama unavailable: connection refused" in output


def test_trace_to_writes_trace_through_trace_writer(monkeypatch, capsys, tmp_path) -> None:
    _patch_startup(monkeypatch)
    monkeypatch.setattr(run_jarvis, "_build_engine", lambda context: _FakeEngine())
    monkeypatch.setattr(run_jarvis, "_timestamp_slug", lambda: "20260427000000")
    monkeypatch.setattr(
        run_jarvis.turn_service,
        "run_text_turn",
        lambda text, *, engine: _fake_result("turn-trace"),
    )

    exit_code = run_jarvis.main(["--text-only", "--trace-to", str(tmp_path)])
    capsys.readouterr()

    assert exit_code == 0
    trace_path = tmp_path / "20260427000000" / "turn-trace.txt"
    assert trace_path.exists()
    assert "turn_id=turn-trace" in trace_path.read_text(encoding="utf-8")


def test_policy_override_is_parsed_and_reported_not_applied(monkeypatch, capsys, tmp_path) -> None:
    _patch_startup(monkeypatch)
    policy_path = tmp_path / "policy.yaml"

    exit_code = run_jarvis.main(["--dry-run", "--policy-override", str(policy_path)])
    output = capsys.readouterr().out

    assert exit_code == 0
    assert f"policy_override={policy_path} status=parsed-not-applied" in output


def test_verbose_dry_run_keeps_fingerprint_first(monkeypatch, capsys) -> None:
    _patch_startup(monkeypatch)

    exit_code = run_jarvis.main(["--verbose", "--dry-run"])
    output = capsys.readouterr().out.splitlines()

    assert exit_code == 0
    assert output[0].startswith("[fingerprint]")
