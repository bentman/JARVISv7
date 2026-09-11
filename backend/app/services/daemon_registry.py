from __future__ import annotations

import contextlib
import json
import os
import secrets
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.app.core.paths import REPO_ROOT

DAEMON_SERVICE = "jarvisv7-backend"
DAEMON_CACHE_DIR = REPO_ROOT / "cache" / "daemon"
DAEMON_METADATA_PATH = DAEMON_CACHE_DIR / "backend.json"
DAEMON_LOCK_PATH = DAEMON_CACHE_DIR / "backend.lock"


class DaemonOwnershipError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DaemonMetadata:
    base_url: str
    host: str
    port: int
    pid: int
    repo_root: str
    started_at: str
    token: str
    owner: dict[str, Any]
    health: dict[str, str]

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "service": DAEMON_SERVICE,
            "base_url": self.base_url,
            "host": self.host,
            "port": self.port,
            "pid": self.pid,
            "repo_root": self.repo_root,
            "started_at": self.started_at,
            "token": self.token,
            "owner": self.owner,
            "health": self.health,
        }




class DaemonRegistry:
    def __init__(
        self,
        *,
        repo_root: Path = REPO_ROOT,
        metadata_path: Path = DAEMON_METADATA_PATH,
        lock_path: Path = DAEMON_LOCK_PATH,
    ) -> None:
        self.repo_root = repo_root.resolve()
        self.metadata_path = metadata_path
        self.lock_path = lock_path

    def read_metadata(self) -> dict[str, Any] | None:
        try:
            raw = self.metadata_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        try:
            metadata = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return metadata if isinstance(metadata, dict) else None

    def status(self) -> dict[str, Any]:
        metadata = self.read_metadata()
        if not metadata:
            return {
                "service": DAEMON_SERVICE,
                "owner": {"state": "unowned"},
                "health": {"status": "unknown", "service": DAEMON_SERVICE},
                "token_present": False,
            }
        token = metadata.get("token")
        public = {key: value for key, value in metadata.items() if key != "token"}
        public["token_present"] = bool(token)
        return public

    def acquire(self, host: str, port: int, *, pid: int | None = None, token: str | None = None) -> DaemonMetadata:
        pid = os.getpid() if pid is None else pid
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self.read_metadata()
        if self._is_live_same_repo_owner(existing, host, port, pid):
            assert existing is not None
            raise DaemonOwnershipError(
                f"live same-repo daemon already owns {host}:{port} "
                f"pid={existing.get('pid')} metadata={self.metadata_path}"
            )
        if existing is not None and self._same_repo_endpoint(existing, host, port):
            self._remove_stale_files()

        try:
            lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            existing = self.read_metadata()
            if self._is_live_same_repo_owner(existing, host, port, pid):
                assert existing is not None
                raise DaemonOwnershipError(
                    f"live same-repo daemon already owns {host}:{port} "
                    f"pid={existing.get('pid')} metadata={self.metadata_path}"
                ) from exc
            self._remove_stale_files()
            lock_fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)

        try:
            os.write(lock_fd, f"{pid}\n".encode())
        finally:
            os.close(lock_fd)

        metadata = DaemonMetadata(
            base_url=f"http://{host}:{port}",
            host=host,
            port=port,
            pid=pid,
            repo_root=str(self.repo_root),
            started_at=datetime.now(UTC).isoformat(),
            token=token or secrets.token_urlsafe(32),
            owner={"state": "owned", "lock_file": str(self.lock_path), "hostname": socket.gethostname()},
            health={"status": "ok", "service": DAEMON_SERVICE},
        )
        self.metadata_path.write_text(
            json.dumps(metadata.to_json(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return metadata

    def release_if_owner(self, *, pid: int | None = None) -> None:
        pid = os.getpid() if pid is None else pid
        metadata = self.read_metadata()
        if metadata is None or metadata.get("pid") != pid:
            return
        self._remove_stale_files()

    def validate_token(self, token: str | None) -> bool:
        if not token:
            return False
        metadata = self.read_metadata()
        expected = metadata.get("token") if metadata else None
        return isinstance(expected, str) and secrets.compare_digest(expected, token)

    def _same_repo_endpoint(self, metadata: dict[str, Any] | None, host: str, port: int) -> bool:
        if metadata is None:
            return False
        try:
            metadata_repo = Path(str(metadata.get("repo_root"))).resolve()
        except (OSError, RuntimeError):
            return False
        return metadata_repo == self.repo_root and metadata.get("host") == host and metadata.get("port") == port

    def _is_live_same_repo_owner(self, metadata: dict[str, Any] | None, host: str, port: int, current_pid: int) -> bool:
        if not self._same_repo_endpoint(metadata, host, port):
            return False
        assert metadata is not None
        owner_pid = metadata.get("pid")
        return isinstance(owner_pid, int) and owner_pid != current_pid and _process_is_alive(owner_pid)

    def _remove_stale_files(self) -> None:
        for path in (self.metadata_path, self.lock_path):
            with contextlib.suppress(FileNotFoundError):
                path.unlink()


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        # Windows has no signal-0 no-op: os.kill() on a nonexistent PID raises
        # OSError WinError 87 rather than the POSIX ProcessLookupError.
        if os.name == "nt" and getattr(exc, "winerror", None) == 87:
            return False
        raise
    return True
