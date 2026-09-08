from __future__ import annotations

import json
import socket
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest
from backend.app.extensions.acp_server import AcpServer, AcpServerConfig, AcpServerSession

# ── AcpServerConfig validation ──────────────────────────────────────


class TestAcpServerConfig:
    def test_default_values(self) -> None:
        config = AcpServerConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 0
        assert config.max_sessions == 5
        assert config.session_timeout_ms == 300_000
        assert config.allowed_tools == ()

    def test_custom_values(self) -> None:
        config = AcpServerConfig(
            host="0.0.0.0",
            port=9999,
            max_sessions=10,
            session_timeout_ms=60_000,
            allowed_tools=("tool_a", "tool_b"),
        )
        assert config.host == "0.0.0.0"
        assert config.port == 9999
        assert config.max_sessions == 10
        assert config.allowed_tools == ("tool_a", "tool_b")

    def test_rejects_empty_host(self) -> None:
        with pytest.raises(ValueError, match="host"):
            AcpServerConfig(host="")

    def test_rejects_negative_port(self) -> None:
        with pytest.raises(ValueError, match="port"):
            AcpServerConfig(port=-1)

    def test_rejects_port_above_65535(self) -> None:
        with pytest.raises(ValueError, match="port"):
            AcpServerConfig(port=70000)

    def test_rejects_zero_max_sessions(self) -> None:
        with pytest.raises(ValueError, match="max_sessions"):
            AcpServerConfig(max_sessions=0)

    def test_rejects_negative_session_timeout(self) -> None:
        with pytest.raises(ValueError, match="session_timeout_ms"):
            AcpServerConfig(session_timeout_ms=0)


# ── AcpServerSession ────────────────────────────────────────────────


class TestAcpServerSession:
    def test_session_defaults(self) -> None:
        session = AcpServerSession(session_id="abc", client_info={"name": "test"})
        assert session.session_id == "abc"
        assert session.client_info == {"name": "test"}
        assert session.status == "active"
        assert session.turn_ids == []
        assert session.created_at  # non-empty ISO timestamp

    def test_session_status_transitions(self) -> None:
        session = AcpServerSession(session_id="s1", client_info={})
        assert session.status == "active"
        session.status = "closed"
        assert session.status == "closed"
        session.status = "timed_out"
        assert session.status == "timed_out"


# ── AcpServer lifecycle ─────────────────────────────────────────────


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestAcpServerLifecycle:
    def test_start_returns_bound_port(self) -> None:
        port = _free_port()
        server = AcpServer(
            AcpServerConfig(port=port),
            turn_engine_getter=lambda: None,
        )
        try:
            bound = server.start()
            assert bound == port
            status = server.status()
            assert status["running"] is True
            assert status["port"] == port
        finally:
            server.stop()

    def test_stop_when_not_running_returns_zero(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        assert server.stop() == 0

    def test_double_start_raises(self) -> None:
        port = _free_port()
        server = AcpServer(
            AcpServerConfig(port=port),
            turn_engine_getter=lambda: None,
        )
        try:
            server.start()
            with pytest.raises(RuntimeError, match="already running"):
                server.start()
        finally:
            server.stop()

    def test_status_when_not_running(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        info = server.status()
        assert info["running"] is False
        assert info["port"] is None
        assert info["active_sessions"] == 0

    def test_list_sessions_empty(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        assert server.list_sessions() == []


# ── Session management ──────────────────────────────────────────────


class TestSessionManagement:
    def test_handle_session_creates_session(self) -> None:
        server = AcpServer(AcpServerConfig(max_sessions=2), turn_engine_getter=lambda: None)
        result = server._handle_session({"name": "test-client"}, {})
        assert "result" in result
        assert "session_id" in result["result"]

    def test_max_sessions_enforced(self) -> None:
        server = AcpServer(AcpServerConfig(max_sessions=1), turn_engine_getter=lambda: None)
        r1 = server._handle_session({"name": "c1"}, {})
        assert "result" in r1

        r2 = server._handle_session({"name": "c2"}, {})
        assert "error" in r2
        assert "max sessions" in r2["error"]["message"]

    def test_handle_message_unknown_session(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        result = server._handle_message("no-such-id", {"text": "hello"})
        assert "error" in result
        assert result["error"]["code"] == -32001

    def test_handle_message_empty_text(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        r = server._handle_session({}, {})
        sid = r["result"]["session_id"]
        result = server._handle_message(sid, {"text": ""})
        assert "error" in result
        assert result["error"]["code"] == -32602

    def test_handle_message_no_engine(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        r = server._handle_session({}, {})
        sid = r["result"]["session_id"]
        result = server._handle_message(sid, {"text": "hello"})
        assert "error" in result
        assert "turn engine" in result["error"]["message"]

    def test_handle_message_routes_through_engine(self) -> None:
        fake_turn = SimpleNamespace(
            turn_id="turn-1",
            response_text="world",
            final_state="IDLE",
        )
        engine = MagicMock()
        engine.run_text_turn.return_value = fake_turn

        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: engine)
        r = server._handle_session({}, {})
        sid = r["result"]["session_id"]

        result = server._handle_message(sid, {"text": "hello"})
        assert "result" in result
        assert result["result"]["turn_id"] == "turn-1"
        assert result["result"]["response"] == "world"
        engine.run_text_turn.assert_called_once_with("hello")

    def test_handle_message_appends_turn_id(self) -> None:
        fake_turn = SimpleNamespace(turn_id="t-42", response_text="ok", final_state="IDLE")
        engine = MagicMock()
        engine.run_text_turn.return_value = fake_turn

        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: engine)
        r = server._handle_session({}, {})
        sid = r["result"]["session_id"]

        server._handle_message(sid, {"text": "msg1"})
        server._handle_message(sid, {"text": "msg2"})

        sessions = server.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["turn_ids"] == ["t-42", "t-42"]

    def test_close_session(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        r = server._handle_session({}, {})
        sid = r["result"]["session_id"]

        result = server._close_session(sid)
        assert result["result"]["closed"] is True

        sessions = server.list_sessions()
        assert sessions[0]["status"] == "closed"

    def test_close_unknown_session(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        result = server._close_session("no-such")
        assert "error" in result

    def test_graceful_shutdown_closes_all_sessions(self) -> None:
        port = _free_port()
        server = AcpServer(AcpServerConfig(port=port, max_sessions=10), turn_engine_getter=lambda: None)
        try:
            server.start()
            server._handle_session({"name": "c1"}, {})
            server._handle_session({"name": "c2"}, {})
            server._handle_session({"name": "c3"}, {})

            assert server.status()["active_sessions"] == 3
        finally:
            closed = server.stop()

        assert closed >= 3
        assert server.status()["running"] is False
        assert server.status()["active_sessions"] == 0


# ── Session timeout ─────────────────────────────────────────────────


class TestSessionTimeout:
    def test_cleanup_marks_expired_sessions(self) -> None:
        server = AcpServer(
            AcpServerConfig(session_timeout_ms=1),
            turn_engine_getter=lambda: None,
        )
        r = server._handle_session({}, {})
        sid = r["result"]["session_id"]

        # Manually back-date the session created_at
        session = server._sessions[sid]
        session.created_at = "2020-01-01T00:00:00+00:00"

        server._cleanup_expired()
        assert server._sessions[sid].status == "timed_out"

    def test_cleanup_does_not_affect_fresh_sessions(self) -> None:
        server = AcpServer(
            AcpServerConfig(session_timeout_ms=60_000),
            turn_engine_getter=lambda: None,
        )
        r = server._handle_session({}, {})
        sid = r["result"]["session_id"]

        server._cleanup_expired()
        assert server._sessions[sid].status == "active"

    def test_timed_out_sessions_excluded_from_active_count(self) -> None:
        server = AcpServer(
            AcpServerConfig(session_timeout_ms=1, max_sessions=5),
            turn_engine_getter=lambda: None,
        )
        r = server._handle_session({}, {})
        sid = r["result"]["session_id"]
        server._sessions[sid].created_at = "2020-01-01T00:00:00+00:00"

        server._cleanup_expired()
        assert server.status()["active_sessions"] == 0

    def test_timed_out_sessions_free_slots_for_new_sessions(self) -> None:
        server = AcpServer(
            AcpServerConfig(session_timeout_ms=1, max_sessions=1),
            turn_engine_getter=lambda: None,
        )
        r1 = server._handle_session({}, {})
        sid = r1["result"]["session_id"]
        server._sessions[sid].created_at = "2020-01-01T00:00:00+00:00"

        # Timeout clears the slot
        r2 = server._handle_session({}, {})
        assert "result" in r2
        assert r2["result"]["session_id"] != sid


# ── Dispatch ────────────────────────────────────────────────────────


class TestDispatch:
    def test_dispatch_initialize(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        result = server._dispatch({"method": "initialize", "params": {"client_info": {"name": "x"}}})
        assert "result" in result
        assert "session_id" in result["result"]

    def test_dispatch_prompt(self) -> None:
        fake_turn = SimpleNamespace(turn_id="t-1", response_text="ok", final_state="IDLE")
        engine = MagicMock()
        engine.run_text_turn.return_value = fake_turn

        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: engine)
        init = server._dispatch({"method": "initialize", "params": {"client_info": {}}})
        sid = init["result"]["session_id"]

        result = server._dispatch({
            "method": "prompt",
            "params": {"session_id": sid, "message": {"text": "hi"}},
        })
        assert "result" in result

    def test_dispatch_prompt_missing_session_id(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        result = server._dispatch({"method": "prompt", "params": {}})
        assert "error" in result

    def test_dispatch_close_session(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        init = server._dispatch({"method": "initialize", "params": {}})
        sid = init["result"]["session_id"]
        result = server._dispatch({"method": "close_session", "params": {"session_id": sid}})
        assert result["result"]["closed"] is True

    def test_dispatch_unknown_method(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        result = server._dispatch({"method": "foobar", "params": {}})
        assert "error" in result
        assert result["error"]["code"] == -32601

    def test_dispatch_handles_non_dict_params(self) -> None:
        server = AcpServer(AcpServerConfig(), turn_engine_getter=lambda: None)
        result = server._dispatch({"method": "initialize", "params": "not-a-dict"})
        # params becomes empty dict when not a dict
        assert "result" in result


# ── TCP integration ─────────────────────────────────────────────────


def _send_json_rpc(port: int, request: dict[str, Any]) -> dict[str, Any]:
    """Send a single JSON-RPC request over TCP and read the response."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.connect(("127.0.0.1", port))
        payload = json.dumps(request) + "\n"
        s.sendall(payload.encode("utf-8"))
        data = b""
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
            if b"\n" in data:
                break
    return json.loads(data.decode("utf-8"))


class TestTcpIntegration:
    def test_initialize_via_tcp(self) -> None:
        port = _free_port()
        server = AcpServer(
            AcpServerConfig(port=port),
            turn_engine_getter=lambda: None,
        )
        try:
            server.start()
            time.sleep(0.1)  # let server accept connections

            response = _send_json_rpc(port, {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"client_info": {"name": "tcp-test"}},
            })
            assert response["jsonrpc"] == "2.0"
            assert response["id"] == 1
            assert "result" in response
            assert "session_id" in response["result"]
        finally:
            server.stop()

    def test_unknown_method_via_tcp(self) -> None:
        port = _free_port()
        server = AcpServer(
            AcpServerConfig(port=port),
            turn_engine_getter=lambda: None,
        )
        try:
            server.start()
            time.sleep(0.1)

            response = _send_json_rpc(port, {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "unknown_method",
                "params": {},
            })
            assert "error" in response
            assert response["error"]["code"] == -32601
        finally:
            server.stop()

    def test_malformed_json_via_tcp(self) -> None:
        port = _free_port()
        server = AcpServer(
            AcpServerConfig(port=port),
            turn_engine_getter=lambda: None,
        )
        try:
            server.start()
            time.sleep(0.1)

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect(("127.0.0.1", port))
                s.sendall(b"this is not json\n")
                data = b""
                while True:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\n" in data:
                        break

            response = json.loads(data.decode("utf-8"))
            assert "error" in response
            assert response["error"]["code"] == -32700
        finally:
            server.stop()

    def test_prompt_via_tcp(self) -> None:
        fake_turn = SimpleNamespace(turn_id="tcp-turn", response_text="pong", final_state="IDLE")
        engine = MagicMock()
        engine.run_text_turn.return_value = fake_turn

        port = _free_port()
        server = AcpServer(
            AcpServerConfig(port=port),
            turn_engine_getter=lambda: engine,
        )
        try:
            server.start()
            time.sleep(0.1)

            # Initialize
            init_resp = _send_json_rpc(port, {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"client_info": {"name": "tcp-client"}},
            })
            sid = init_resp["result"]["session_id"]

            # Prompt
            prompt_resp = _send_json_rpc(port, {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "prompt",
                "params": {"session_id": sid, "message": {"text": "ping"}},
            })
            assert "result" in prompt_resp
            assert prompt_resp["result"]["turn_id"] == "tcp-turn"
            assert prompt_resp["result"]["response"] == "pong"
        finally:
            server.stop()
