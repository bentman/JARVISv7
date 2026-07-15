from __future__ import annotations

from pathlib import Path

from backend.app.tools.registry import ToolBase


class FilesystemReadTool(ToolBase):
    def __init__(self, sandbox_root: Path) -> None:
        self._sandbox_root = sandbox_root.resolve()

    def name(self) -> str:
        return "filesystem.read"

    def description(self) -> str:
        return "Read UTF-8 text files from the configured sandbox path only."

    def run(self, tool_input: dict[str, object]) -> str:
        raw_path = tool_input.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return "ERROR: missing required 'path' string"

        try:
            requested = Path(raw_path)
            candidate = (self._sandbox_root / requested).resolve()

            if not candidate.is_relative_to(self._sandbox_root):
                return "ERROR: path outside sandbox"
            if not candidate.exists() or not candidate.is_file():
                return "ERROR: file not found"
            return candidate.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return "ERROR: file is not valid UTF-8 text"
        except ValueError:
            return "ERROR: invalid path"
        except Exception:
            return "ERROR: filesystem read failed"
