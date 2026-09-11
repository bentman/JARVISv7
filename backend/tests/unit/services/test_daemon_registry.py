from __future__ import annotations

import os
from pathlib import Path

import pytest
from backend.app.services.daemon_registry import DaemonOwnershipError, DaemonRegistry


def _registry(tmp_path: Path) -> DaemonRegistry:
    return DaemonRegistry(
        repo_root=tmp_path,
        metadata_path=tmp_path / "cache" / "daemon" / "backend.json",
        lock_path=tmp_path / "cache" / "daemon" / "backend.lock",
    )


def test_acquire_writes_ephemeral_metadata_and_token(tmp_path: Path) -> None:
    registry = _registry(tmp_path)

    metadata = registry.acquire("127.0.0.1", 8765, token="local-token")

    payload = registry.read_metadata()
    assert payload is not None
    assert payload["base_url"] == "http://127.0.0.1:8765"
    assert payload["host"] == "127.0.0.1"
    assert payload["port"] == 8765
    assert payload["pid"] == os.getpid()
    assert payload["repo_root"] == str(tmp_path.resolve())
    assert payload["token"] == "local-token"
    assert payload["owner"]["state"] == "owned"
    assert payload["health"] == {"status": "ok", "service": "jarvisv7-backend"}
    assert registry.lock_path.read_text(encoding="utf-8").strip() == str(os.getpid())
    assert metadata.base_url == "http://127.0.0.1:8765"


def test_stale_same_repo_metadata_is_replaced(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.acquire("127.0.0.1", 8765, pid=999999, token="stale")

    metadata = registry.acquire("127.0.0.1", 8765, token="fresh")

    payload = registry.read_metadata()
    assert payload is not None
    assert metadata.token == "fresh"
    assert payload["token"] == "fresh"
    assert payload["pid"] == os.getpid()


def test_live_same_repo_owner_conflicts(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("backend.app.services.daemon_registry._process_is_alive", lambda pid: True)
    registry = _registry(tmp_path)
    registry.acquire("127.0.0.1", 8765, token="owner")

    with pytest.raises(DaemonOwnershipError, match="live same-repo daemon already owns"):
        registry.acquire("127.0.0.1", 8765, pid=os.getpid() + 1, token="other")


def test_token_validation_uses_metadata_token(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.acquire("127.0.0.1", 8765, token="expected")

    assert registry.validate_token("expected") is True
    assert registry.validate_token("wrong") is False
    assert registry.validate_token(None) is False


def test_status_omits_token_value(tmp_path: Path) -> None:
    registry = _registry(tmp_path)
    registry.acquire("127.0.0.1", 8765, token="secret-token")

    status = registry.status()

    assert "token" not in status
    assert status["token_present"] is True
    assert status["owner"]["state"] == "owned"
