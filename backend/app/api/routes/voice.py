from __future__ import annotations

import io
import wave

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request

from backend.app.api.dependencies import get_engine
from backend.app.api.schemas.voice import VoiceTurnResponse
from backend.app.conversation.engine import TurnEngine, TurnResult
from backend.app.services import turn_service

router = APIRouter()


def decode_wav_bytes(payload: bytes) -> tuple[np.ndarray, int]:
    try:
        with wave.open(io.BytesIO(payload), "rb") as wav_file:
            channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            sample_rate = wav_file.getframerate()
            frames = wav_file.readframes(wav_file.getnframes())
    except wave.Error as exc:
        raise ValueError(f"invalid wav audio: {exc}") from exc

    if sample_width == 1:
        audio = (np.frombuffer(frames, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        audio = np.frombuffer(frames, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 4:
        audio = np.frombuffer(frames, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise ValueError(f"unsupported wav sample width: {sample_width}")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    return np.asarray(audio, dtype=np.float32).reshape(-1), sample_rate


def voice_turn_response(result: TurnResult) -> VoiceTurnResponse:
    return VoiceTurnResponse(
        turn_id=result.turn_id,
        session_id=result.session_id,
        transcript=result.transcript,
        response_text=result.response_text,
        final_state=result.final_state.value,
        failure_reason=result.failure_reason,
        tts_degraded=result.tts_degraded,
        tts_degraded_reason=result.tts_degraded_reason,
        interrupted=result.interrupted,
        interruption_events=result.interruption_events,
    )


@router.post("/task/voice", response_model=VoiceTurnResponse)
async def voice_turn(request: Request, engine: TurnEngine = Depends(get_engine)) -> VoiceTurnResponse:
    payload = await request.body()
    if not payload:
        raise HTTPException(status_code=400, detail="audio body is empty")
    try:
        audio, sample_rate = decode_wav_bytes(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = turn_service.run_voice_turn(audio, sample_rate, engine=engine)
    return voice_turn_response(result)