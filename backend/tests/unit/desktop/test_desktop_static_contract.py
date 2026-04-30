from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
DESKTOP = REPO_ROOT / "desktop"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def test_required_desktop_files_exist() -> None:
    for relative_path in [
        "desktop/package.json",
        "desktop/src/index.html",
        "desktop/src/main.js",
        "desktop/src/style.css",
        "desktop/src-tauri/Cargo.toml",
        "desktop/src-tauri/build.rs",
        "desktop/src-tauri/tauri.conf.json",
        "desktop/src-tauri/src/main.rs",
        "desktop/src-tauri/src/lib.rs",
        "desktop/src-tauri/src/backend.rs",
        "desktop/src-tauri/icons/icon.ico",
    ]:
        assert (REPO_ROOT / relative_path).is_file(), relative_path


def test_tauri_config_uses_desktop_icon_and_tray_code_exists() -> None:
    config = _read("desktop/src-tauri/tauri.conf.json")
    lib_rs = _read("desktop/src-tauri/src/lib.rs")
    cargo_toml = _read("desktop/src-tauri/Cargo.toml")
    assert "icons/icon.ico" in config
    assert "\"icon\": [\"icons/icon.ico\"]" in config
    assert "tray-icon" in cargo_toml
    assert "TrayIconBuilder" in lib_rs
    for label in ["Start Backend", "Stop Backend", "Show Window", "Quit"]:
        assert label in lib_rs
    assert "start_backend(state)" in lib_rs
    assert "stop_backend(state)" in lib_rs
    assert "get_webview_window" in lib_rs
    assert '"quit"' in lib_rs


def test_backend_lifecycle_uses_run_backend_not_proving_host() -> None:
    combined = _read("desktop/src-tauri/src/backend.rs") + _read("desktop/src-tauri/src/lib.rs")
    assert "run_backend.py" in combined
    assert "run_jarvis.py" not in combined


def test_backend_lifecycle_uses_repo_local_python_and_fixed_host_port() -> None:
    backend_rs = _read("desktop/src-tauri/src/backend.rs")
    assert "backend" in backend_rs
    assert ".venv" in backend_rs
    assert "Scripts" in backend_rs
    assert "python.exe" in backend_rs
    assert "127.0.0.1" in backend_rs
    assert "8765" in backend_rs
    assert "current_dir(&self.repo_root)" in backend_rs


def test_desktop_references_only_approved_d1_endpoints_for_first_pass() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            DESKTOP / "src-tauri" / "src" / "backend.rs",
            DESKTOP / "src-tauri" / "src" / "lib.rs",
            DESKTOP / "src" / "main.js",
        ]
    )
    for endpoint in ["/health", "/readiness", "/session/create", "/session/close", "/session/status", "/status/wake", "/personality/list", "/personality/select", "/task/text", "/task/voice"]:
        assert endpoint in source
    assert "/session/tick" not in source
    assert "/session/ptt" not in source
    assert "websocket" not in source.lower()


def test_desktop_displays_resident_session_status() -> None:
    backend_rs = _read("desktop/src-tauri/src/backend.rs")
    lib_rs = _read("desktop/src-tauri/src/lib.rs")
    main_js = _read("desktop/src/main.js")
    index_html = _read("desktop/src/index.html")
    assert "get_session_status" in backend_rs
    assert "/session/status" in backend_rs
    assert "get_session_status" in lib_rs
    assert "generate_handler![start_backend, stop_backend, health_check, get_readiness, get_session_status" in lib_rs
    assert 'invoke("get_session_status")' in main_js
    assert "refreshSessionStatus" in main_js
    assert "session-turn-count" in main_js
    assert "session-turn-count" in index_html


def test_desktop_displays_wake_status_and_ptt_fallback() -> None:
    backend_rs = _read("desktop/src-tauri/src/backend.rs")
    lib_rs = _read("desktop/src-tauri/src/lib.rs")
    main_js = _read("desktop/src/main.js")
    index_html = _read("desktop/src/index.html")
    assert "get_wake_status" in backend_rs
    assert "/status/wake" in backend_rs
    assert "get_wake_status" in lib_rs
    assert "generate_handler![start_backend, stop_backend, health_check, get_readiness, get_session_status, get_wake_status" in lib_rs
    assert 'invoke("get_wake_status")' in main_js
    assert "refreshWakeStatus" in main_js
    assert "PTT-only fallback" in main_js
    assert "wake-status" in index_html
    assert "wake-detail" in index_html


def test_desktop_displays_personality_selector_and_presence_ui() -> None:
    backend_rs = _read("desktop/src-tauri/src/backend.rs")
    lib_rs = _read("desktop/src-tauri/src/lib.rs")
    main_js = _read("desktop/src/main.js")
    index_html = _read("desktop/src/index.html")
    assert "/personality/list" in backend_rs
    assert "/personality/select" in backend_rs
    assert "get_personality_list" in lib_rs
    assert "select_personality" in lib_rs
    assert 'invoke("get_personality_list")' in main_js
    assert 'invoke("select_personality"' in main_js
    assert "personality-select" in index_html
    assert "personality-current" in index_html
    assert "appendPresence" in main_js
    assert "presenceByProfile" in main_js
    assert "submit_text_turn" in backend_rs


def test_voice_path_uses_raw_wav_not_multipart_and_maps_visible_results() -> None:
    backend_rs = _read("desktop/src-tauri/src/backend.rs")
    main_js = _read("desktop/src/main.js")
    assert "POST /task/voice" in backend_rs
    assert "application/octet-stream" in backend_rs
    assert "multipart" not in backend_rs.lower()
    for token in ["RIFF", "WAVE", "fmt ", "data"]:
        assert token in main_js
    for field in ["transcript", "response_text", "final_state", "failure_reason", "tts_degraded", "tts_degraded_reason", "interrupted", "interruption_events"]:
        assert field in main_js
    assert "getUserMedia" in main_js
    assert "MediaRecorder" in main_js
    assert "audioBytes" in main_js
    assert "/stream" not in backend_rs.lower()
    assert "websocket" not in backend_rs.lower()


def test_no_tools_or_agents_implementation_calls() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in [
            DESKTOP / "src-tauri" / "src" / "backend.rs",
            DESKTOP / "src-tauri" / "src" / "lib.rs",
            DESKTOP / "src" / "main.js",
        ]
    )
    assert "/agents" not in source
    assert "/tools" not in source
    assert "tool_registry" not in source


def test_backend_startup_diagnostics_are_exposed() -> None:
    backend_rs = _read("desktop/src-tauri/src/backend.rs")
    for expected in [
        "python_path",
        "backend_script_path",
        "working_directory",
        "host",
        "port",
        "backend_startup.log",
        "backend_spawn_stderr.log",
        "try_wait",
    ]:
        assert expected in backend_rs