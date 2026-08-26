from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

import pytest
from backend.tests.conftest import SKIP_UNLESS_LIVE

BACKEND_BASE_URL = os.getenv("JARVISV7_BACKEND_URL", "http://127.0.0.1:8765").rstrip("/")


def _request_json(method: str, path: str, payload: dict[str, object] | None = None, *, timeout_s: float = 10.0) -> tuple[int, dict[str, object]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=f"{BACKEND_BASE_URL}{path}",
        data=body,
        method=method,
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            return response.getcode(), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_text = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(error_text)
        except json.JSONDecodeError:
            return exc.code, {"detail": error_text}


def _assert_backend_reachable() -> None:
    try:
        status, payload = _request_json("GET", "/health", timeout_s=3.0)
    except urllib.error.URLError:
        pytest.skip(f"desktop live proof requires the desktop-started backend at {BACKEND_BASE_URL}")
    if status != 200:
        pytest.skip(f"desktop live proof requires backend at {BACKEND_BASE_URL}; /health returned {status}: {payload}")


def _wait_for(predicate, *, timeout_s: float, reason: str) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    last_payload: dict[str, object] = {}
    while time.monotonic() < deadline:
        status, payload = _request_json("GET", "/session/status")
        if status == 200:
            last_payload = payload
            if predicate(payload):
                return payload
        time.sleep(0.25)
    raise AssertionError(f"{reason}; diagnostics={_desktop_status_diagnostics(last_payload)}")


def _wait_for_resident_status(predicate, *, timeout_s: float, reason: str) -> dict[str, object]:
    deadline = time.monotonic() + timeout_s
    last_payload: dict[str, object] = {}
    while time.monotonic() < deadline:
        status, payload = _request_json("GET", "/status/resident-voice")
        if status == 200:
            last_payload = payload
            if predicate(payload):
                return payload
        time.sleep(0.25)
    raise AssertionError(f"{reason}; diagnostics={_desktop_status_diagnostics(resident_status=last_payload)}")


def _desktop_status_diagnostics(session_status: dict[str, object] | None = None, *, resident_status: dict[str, object] | None = None) -> str:
    diagnostics: dict[str, object] = {}
    diagnostics["session"] = session_status or _safe_get_json("/session/status")
    diagnostics["resident_voice"] = resident_status or _safe_get_json("/status/resident-voice")
    diagnostics["wake"] = _safe_get_json("/status/wake")
    return json.dumps(diagnostics, sort_keys=True)


def _safe_get_json(path: str) -> dict[str, object]:
    try:
        status, payload = _request_json("GET", path, timeout_s=3.0)
    except Exception as exc:
        return {"error": str(exc)}
    payload = dict(payload)
    payload["_http_status"] = status
    return payload


def _operator_notice(capsys, title: str, lines: list[str]) -> None:
    with capsys.disabled():
        print(f"\n[operator] {title}", flush=True)
        print(f"[operator] backend={BACKEND_BASE_URL}", flush=True)
        for line in lines:
            print(f"[operator] {line}", flush=True)


@pytest.mark.live
@pytest.mark.desktop
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_desktop_resident_ptt_and_hands_free_are_visible_through_backend_status(capsys) -> None:
    _assert_backend_reachable()
    _operator_notice(
        capsys,
        "Desktop resident voice validation",
        [
            "Start the desktop app and confirm the Operator panel is visible.",
            "Set resident mode to Hands-free in the desktop resident voice selector.",
            "Click Start Voice and speak a short request.",
            "When the desktop remains in hands-free follow-up listening, speak one follow-up request.",
        ],
    )

    resident_status = _wait_for_resident_status(
        lambda status: status.get("mode") in {"hands-free", "continuous"}
        and status.get("stream_running") is True
        and status.get("ptt_supported") is True,
        timeout_s=90.0,
        reason="desktop did not expose an active hands-free/continuous resident mode",
    )

    payload = _wait_for(
        lambda status: status.get("invocation_source") in {"hands_free", "continuous"}
        and status.get("state") == "IDLE"
        and bool(status.get("last_transcript")),
        timeout_s=90.0,
        reason="desktop hands-free/continuous follow-up did not complete",
    )

    resident_status_code, resident_status = _request_json("GET", "/status/resident-voice")
    assert resident_status_code == 200
    assert resident_status.get("follow_up_listening") is False, resident_status
    assert resident_status.get("continuous_active") is (resident_status.get("mode") == "continuous")
    assert payload["failure_reason"] is None
