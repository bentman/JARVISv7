from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import pytest
from backend.tests.conftest import SKIP_UNLESS_LIVE

BACKEND_BASE_URL = os.getenv("JARVISV7_BACKEND_URL", "http://127.0.0.1:8765").rstrip("/")
LIVE_TIMEOUT_S = float(os.getenv("JARVISV7_LIVE_TIMEOUT_S", "60"))


def _request_json(method: str, path: str, payload: dict[str, object] | None = None, *, timeout_s: float = 10) -> tuple[int, dict[str, object]]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url=f"{BACKEND_BASE_URL}{path}",
        data=body,
        method=method,
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = response.getcode()
            data = json.loads(response.read().decode("utf-8"))
            return status, data
    except urllib.error.HTTPError as exc:
        error_text = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(error_text)
        except json.JSONDecodeError:
            return exc.code, {"detail": error_text}


def _assert_backend_reachable() -> None:
    request = urllib.request.Request(url=f"{BACKEND_BASE_URL}/health", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            if response.getcode() != 200:
                pytest.skip(f"live desktop harness requires backend at {BACKEND_BASE_URL}; /health returned {response.getcode()}")
    except urllib.error.URLError:
        pytest.skip(f"live desktop harness requires backend at {BACKEND_BASE_URL}; backend is not reachable")


@pytest.mark.live
@pytest.mark.desktop
@pytest.mark.skipif(SKIP_UNLESS_LIVE, reason="JARVISV7_LIVE_TESTS not set")
def test_three_consecutive_turns_in_resident_session_complete_without_error() -> None:
    print(f"[desktop-live] backend={BACKEND_BASE_URL}")
    print(f"[desktop-live] text_turn_timeout_s={LIVE_TIMEOUT_S}")
    _assert_backend_reachable()
    create_status, create_payload = _request_json("POST", "/session/create", {})
    print(f"[desktop-live] session/create status={create_status} payload={create_payload}")
    assert create_status == 200
    session_id = str(create_payload["session_id"])

    turn_session_ids: list[str] = []
    for index in range(1, 4):
        print(f"[desktop-live] turn={index} session={session_id} request_start endpoint=/task/text timeout_s={LIVE_TIMEOUT_S}")
        try:
            turn_status, turn_payload = _request_json(
                "POST",
                "/task/text",
                {"session_id": session_id, "text": f"live turn {index}: reply with ready"},
                timeout_s=LIVE_TIMEOUT_S,
            )
        except TimeoutError as exc:
            raise AssertionError(
                f"timeout calling /task/text after {LIVE_TIMEOUT_S}s (session_id={session_id}, turn_index={index})"
            ) from exc
        print(f"[desktop-live] task/text #{index} status={turn_status} session={turn_payload.get('session_id')}")
        print(f"[desktop-live] turn={index} response status={turn_status} payload_keys={sorted(turn_payload.keys())}")
        assert turn_status == 200
        turn_session_ids.append(str(turn_payload["session_id"]))

    status_code, status_payload = _request_json("GET", "/session/status")
    print(f"[desktop-live] session/status status={status_code} payload={status_payload}")
    assert status_code == 200

    close_status, close_payload = _request_json("POST", "/session/close", {"session_id": session_id})
    print(f"[desktop-live] session/close status={close_status} payload={close_payload}")
    assert close_status == 200

    assert len(turn_session_ids) == 3
    assert set(turn_session_ids) == {session_id}
    assert status_payload["active"] is True
    turn_count = status_payload.get("turn_count")
    assert isinstance(turn_count, int)
    assert turn_count >= 3
