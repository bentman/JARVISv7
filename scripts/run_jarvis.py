from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.artifacts.trace_writer import write_trace
from backend.app.conversation.engine import TurnEngine, TurnResult
from backend.app.conversation.states import ConversationState
from backend.app.core.capabilities import FullCapabilityReport, HardwareProfile
from backend.app.core.logging import configure_logging, emit_host_fingerprint
from backend.app.hardware.preflight import PreflightResult, run_preflight
from backend.app.hardware.profiler import run_profiler
from backend.app.hardware.provisioning import resolve_required_extras
from backend.app.hardware.readiness import (
    derive_llm_device_readiness,
    derive_stt_device_readiness,
    derive_tts_device_readiness,
    derive_wake_device_readiness,
)
from backend.app.personality.loader import load_default_personality
from backend.app.runtimes.llm.ollama_runtime import OllamaLLM
from backend.app.runtimes.stt.stt_runtime import select_stt_runtime
from backend.app.runtimes.tts.tts_runtime import select_tts_runtime
from backend.app.services import turn_service, voice_service


TEXT_DIAGNOSTIC_PROMPT = "Briefly confirm JARVIS proving-host text path is operational."


@dataclass(slots=True)
class StartupContext:
    report: FullCapabilityReport
    profile: HardwareProfile
    extras: list[str]
    preflight: PreflightResult
    readiness: dict[str, tuple[str, bool, str]]
    readiness_summary: str


def _timestamp_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="run_jarvis.py")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--trace-to", type=Path)
    parser.add_argument("--profile", action="store_true")
    parser.add_argument("--turns", type=int, default=1)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--voice-only", action="store_true")
    mode.add_argument("--text-only", action="store_true")
    parser.add_argument("--policy-override", type=Path)
    args = parser.parse_args(argv)
    if args.turns < 1:
        parser.error("--turns must be >= 1")
    return args


def _readiness_summary(preflight: PreflightResult) -> str:
    status = "ready" if not preflight.probe_errors else "degraded"
    return f"{status}; tokens={len(preflight.tokens)}"


def _load_startup_context() -> StartupContext:
    report = run_profiler()
    profile = report.profile
    extras = resolve_required_extras(profile)
    preflight = run_preflight(profile, extras)
    readiness = {
        "stt": derive_stt_device_readiness(preflight, profile),
        "tts": derive_tts_device_readiness(preflight, profile),
        "llm": derive_llm_device_readiness(preflight, profile),
        "wake": derive_wake_device_readiness(preflight, profile),
    }
    return StartupContext(
        report=report,
        profile=profile,
        extras=extras,
        preflight=preflight,
        readiness=readiness,
        readiness_summary=_readiness_summary(preflight),
    )


def _emit_fallback_fingerprint(readiness: str, out: TextIO) -> None:
    profile = type("Profile", (), {"arch": "unknown", "profiled_at": "unknown"})()
    emit_host_fingerprint(profile, [], readiness=readiness, out=out)


def _family_for(name: str) -> str:
    return {
        "stt": "onnx-whisper",
        "tts": "kokoro-onnx",
        "llm": "ollama",
        "wake": "openwakeword",
    }[name]


def _print_startup_plan(context: StartupContext, args: argparse.Namespace, out: TextIO) -> None:
    mode = _mode_name(args)
    print("JARVISv7 proving host startup", file=out)
    print(f"mode={mode}", file=out)
    if args.policy_override is not None:
        print(f"policy_override={args.policy_override} status=parsed-not-applied", file=out)
    profile_id = getattr(context.profile, "profile_id", "unknown")
    print(f"profile_id={profile_id}", file=out)
    flags = getattr(context.report, "flags", None)
    if flags is not None:
        print(
            "capabilities "
            f"supports_local_stt={getattr(flags, 'supports_local_stt', False)} "
            f"supports_local_tts={getattr(flags, 'supports_local_tts', False)} "
            f"supports_local_llm={getattr(flags, 'supports_local_llm', False)} "
            f"supports_wake_word={getattr(flags, 'supports_wake_word', False)} "
            f"requires_degraded_mode={getattr(flags, 'requires_degraded_mode', False)}",
            file=out,
        )
    for extra in context.extras:
        print(f"extra {extra}: selected", file=out)
    print(
        f"preflight tokens={len(context.preflight.tokens)} probe_errors={len(context.preflight.probe_errors)}",
        file=out,
    )
    for name, (device, available, reason) in context.readiness.items():
        print(
            f"readiness {name} family={_family_for(name)} model=selected-by-runtime "
            f"device={device} available={available} reason={reason}",
            file=out,
        )
    if context.preflight.probe_errors:
        for key, value in sorted(context.preflight.probe_errors.items()):
            print(f"READINESS_UNVERIFIED {key}: {value}", file=out)


def _mode_name(args: argparse.Namespace) -> str:
    if args.dry_run:
        return "dry-run"
    if args.profile:
        return "profile"
    if args.voice_only:
        return "voice"
    return "text"


def _build_engine(context: StartupContext) -> TurnEngine:
    stt = select_stt_runtime(context.preflight, context.profile)
    tts = select_tts_runtime(context.preflight, context.profile)
    llm = OllamaLLM()
    personality = load_default_personality()
    return TurnEngine(stt=stt, tts=tts, llm=llm, personality=personality)


def _build_trace_dir(trace_to: Path | None) -> Path | None:
    if trace_to is None:
        return None
    return trace_to / _timestamp_slug()


def _trace_result(result: TurnResult, trace_dir: Path | None) -> None:
    if trace_dir is None:
        return
    content = "\n".join(
        [
            f"turn_id={result.turn_id}",
            f"session_id={result.session_id}",
            f"final_state={result.final_state.value}",
            f"failure_reason={result.failure_reason}",
            f"transcript={result.transcript}",
            f"response_text={result.response_text}",
        ]
    )
    write_trace(result.turn_id, content, trace_dir)


def _print_result(result: TurnResult, out: TextIO) -> None:
    print(f"turn {result.turn_id} final_state={result.final_state.value}", file=out)
    if result.transcript is not None:
        print(f"transcript={result.transcript}", file=out)
    if result.response_text is not None:
        print(f"response_text={result.response_text}", file=out)
    if result.tts_degraded:
        print(f"TTS_UNAVAILABLE {result.tts_degraded_reason}", file=out)
    if result.failure_reason:
        print(f"failure_reason={result.failure_reason}", file=out)


def _is_model_missing(reason: str) -> bool:
    lowered = reason.lower()
    return "model" in lowered and any(token in lowered for token in ("missing", "not found", "no such"))


def _run_text_turns(
    context: StartupContext,
    args: argparse.Namespace,
    trace_dir: Path | None,
    out: TextIO,
) -> int:
    engine = _build_engine(context)
    llm = getattr(engine, "llm", None)
    if llm is not None and hasattr(llm, "is_available") and not llm.is_available():
        reason = getattr(llm, "reason", "LLM runtime unavailable")
        print(f"LLM_UNAVAILABLE {reason}", file=out)
        return 1
    for index in range(args.turns):
        if args.verbose:
            print(f"phase=text_turn_start index={index + 1}", file=out)
        result = turn_service.run_text_turn(TEXT_DIAGNOSTIC_PROMPT, engine=engine)
        _trace_result(result, trace_dir)
        _print_result(result, out)
        if result.failure_reason:
            if _is_model_missing(result.failure_reason):
                print(f"MODEL_MISSING {result.failure_reason}", file=out)
            else:
                print(f"LLM_UNAVAILABLE {result.failure_reason}", file=out)
            return 1
    return 0


def _run_voice_turns(
    context: StartupContext,
    args: argparse.Namespace,
    trace_dir: Path | None,
    out: TextIO,
) -> int:
    _device, stt_available, stt_reason = context.readiness["stt"]
    if not stt_available:
        print(f"STT_UNAVAILABLE {stt_reason}", file=out)
        return 1
    engine = _build_engine(context)
    llm = getattr(engine, "llm", None)
    if llm is not None and hasattr(llm, "is_available") and not llm.is_available():
        reason = getattr(llm, "reason", "LLM runtime unavailable")
        print(f"LLM_UNAVAILABLE {reason}", file=out)
        return 1
    for index in range(args.turns):
        if args.verbose:
            print(f"phase=voice_capture_start index={index + 1}", file=out)
        try:
            audio, sample_rate = voice_service.capture_audio(duration_s=3.0)
        except voice_service.AudioCaptureError as exc:
            print(f"AUDIO_DEVICE_ERROR {exc}", file=out)
            return 1
        if args.verbose:
            print(f"phase=voice_turn_start index={index + 1}", file=out)
        result = turn_service.run_voice_turn(audio, sample_rate, engine=engine)
        _trace_result(result, trace_dir)
        _print_result(result, out)
        if result.failure_reason:
            if _is_model_missing(result.failure_reason):
                print(f"MODEL_MISSING {result.failure_reason}", file=out)
            else:
                print(f"STT_UNAVAILABLE {result.failure_reason}", file=out)
            return 1
    return 0


def main(argv: list[str] | None = None, out: TextIO | None = None) -> int:
    output = out or sys.stdout
    args = _parse_args(sys.argv[1:] if argv is None else argv)
    configure_logging(level="DEBUG" if args.verbose else "INFO", trace_to=args.trace_to)

    try:
        context = _load_startup_context()
    except Exception as exc:
        _emit_fallback_fingerprint("profile-failed", output)
        print(f"PROFILER_UNAVAILABLE {exc}", file=output)
        return 1

    emit_host_fingerprint(
        context.profile,
        context.extras,
        readiness=context.readiness_summary,
        out=output,
    )
    _print_startup_plan(context, args, output)

    if args.dry_run or args.profile:
        return 0
    if context.preflight.probe_errors:
        print("READINESS_UNVERIFIED preflight probe errors present", file=output)
        return 1

    trace_dir = _build_trace_dir(args.trace_to)
    if args.voice_only:
        return _run_voice_turns(context, args, trace_dir, output)
    return _run_text_turns(context, args, trace_dir, output)


if __name__ == "__main__":
    raise SystemExit(main())