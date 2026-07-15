from __future__ import annotations

from pathlib import Path

from backend.app.tools.filesystem.read_tool import FilesystemReadTool


def test_filesystem_read_returns_file_contents(tmp_path: Path) -> None:
    sandbox = tmp_path / "tool_sandbox"
    sandbox.mkdir()
    target = sandbox / "note.txt"
    target.write_text("hello", encoding="utf-8")
    tool = FilesystemReadTool(sandbox)
    assert tool.run({"path": "note.txt"}) == "hello"


def test_filesystem_read_refuses_outside_and_sibling_data_dirs(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    sandbox = data_root / "tool_sandbox"
    sandbox.mkdir(parents=True)
    for sibling in ["memory", "sessions", "turns", "agents"]:
        d = data_root / sibling
        d.mkdir(parents=True)
        (d / "x.txt").write_text("nope", encoding="utf-8")
    tool = FilesystemReadTool(sandbox)
    assert tool.run({"path": "../memory/x.txt"}).startswith("ERROR")
    assert tool.run({"path": "../sessions/x.txt"}).startswith("ERROR")
    assert tool.run({"path": "../turns/x.txt"}).startswith("ERROR")
    assert tool.run({"path": "../agents/x.txt"}).startswith("ERROR")


def test_filesystem_read_nul_byte_path_returns_error_string(tmp_path: Path) -> None:
    sandbox = tmp_path / "tool_sandbox"
    sandbox.mkdir()
    tool = FilesystemReadTool(sandbox)
    assert tool.run({"path": "bad\x00name.txt"}) == "ERROR: invalid path"


def test_filesystem_read_missing_and_binary_fail_closed(tmp_path: Path) -> None:
    sandbox = tmp_path / "tool_sandbox"
    sandbox.mkdir()
    tool = FilesystemReadTool(sandbox)
    assert tool.run({"path": "missing.txt"}) == "ERROR: file not found"
    bad = sandbox / "bad.bin"
    bad.write_bytes(b"\xff\xfe\x00")
    assert tool.run({"path": "bad.bin"}).startswith("ERROR")
