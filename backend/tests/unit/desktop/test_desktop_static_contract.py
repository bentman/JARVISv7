from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
DESKTOP = REPO_ROOT / "desktop"


def _read(relative_path: str) -> str:
    return (REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _css_outside_token_section() -> str:
    style_css = _read("desktop/src/style.css")
    start = "/* JARVIS_V7_TOKENS_START */"
    end = "/* JARVIS_V7_TOKENS_END */"
    assert start in style_css
    assert end in style_css
    before, rest = style_css.split(start, 1)
    _, after = rest.split(end, 1)
    return before + after


def test_required_desktop_files_exist() -> None:
    for relative_path in [
        "desktop/package.json",
        "desktop/src/index.html",
        "desktop/src/main.js",
        "desktop/src/components/settings-panel.js",
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
    wake_indicator = _read("desktop/src/components/wake-indicator.js")
    assert "get_wake_status" in backend_rs
    assert "/status/wake" in backend_rs
    assert "get_wake_status" in lib_rs
    assert "generate_handler![start_backend, stop_backend, health_check, get_readiness, get_session_status, get_wake_status" in lib_rs
    assert 'invoke("get_wake_status")' in main_js
    assert "refreshWakeStatus" in main_js
    assert "./components/wake-indicator.js" in main_js
    assert "renderWakeStatus(status, wakeIndicatorEl)" in main_js
    assert "PTT-only fallback" in main_js
    assert 'id="wake-indicator"' in index_html
    assert "wake-status" not in index_html
    assert "wake-detail" not in index_html
    assert "export function renderWakeStatus" in wake_indicator
    for field in ["provider", "available", "monitoring", "reason"]:
        assert field in wake_indicator


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
    assert 'personalitySelectEl.addEventListener("change"' in main_js
    assert "selectPersonality(event.target.value)" in main_js
    assert "updatePersonalityDisplay(payload.active)" in main_js
    assert "function updatePersonalityDisplay(profile)" in main_js
    assert "personalityDetailEl.replaceChildren" in main_js
    for label in ["Tone", "Brevity", "Formality"]:
        assert label in main_js
    for field in ["profile.tone", "profile.brevity", "profile.formality"]:
        assert field in main_js
    assert "value || \"—\"" in main_js
    assert "personalityDetailEl.innerHTML" not in main_js


def test_k2b_settings_panel_component_and_shell_wiring() -> None:
    index_html = _read("desktop/src/index.html")
    main_js = _read("desktop/src/main.js")
    settings_panel = _read("desktop/src/components/settings-panel.js")

    assert 'id="settings-trigger"' in index_html
    assert 'id="settings-panel"' in index_html
    assert "./components/settings-panel.js" in main_js
    assert "openSettings(settingsPanelEl" in main_js
    assert "closeSettings()" in main_js
    assert "export async function openSettings" in settings_panel
    assert "export function closeSettings" in settings_panel
    assert 'fetch(CONFIG_ENDPOINT)' in settings_panel
    assert 'method: "POST"' in settings_panel
    assert "http://127.0.0.1:8765/config/operator" in settings_panel
    assert "innerHTML" not in settings_panel
    assert "textContent" in settings_panel
    for field in ["restart_required", "secret", "has_value", "editable", "description"]:
        assert field in settings_panel
    for copy in ["Unsaved changes", "restart required", "written", "rejected", ".env is required"]:
        assert copy in settings_panel
    assert "payload.fields" in settings_panel


def test_k2c_settings_restart_required_ux_contract() -> None:
    index_html = _read("desktop/src/index.html")
    main_js = _read("desktop/src/main.js")
    settings_panel = _read("desktop/src/components/settings-panel.js")

    assert 'id="settings-restart-required"' in index_html
    assert "Restart required" in index_html
    assert "restartBackendForSettings" in main_js
    assert 'invoke("stop_backend")' in main_js
    assert 'invoke("start_backend")' in main_js
    assert 'invoke("get_readiness")' in main_js
    assert "renderReadiness(readiness)" in main_js
    assert "restartBackend: restartBackendForSettings" in main_js
    assert "onRestartRequiredChange: updateSettingsRestartRequired" in main_js
    assert "settingsRestartRequiredEl.hidden" in main_js
    assert "export async function openSettings(containerEl, options = {})" in settings_panel
    assert "restartHandler = options.restartBackend" in settings_panel
    assert "restartRequiredChangeHandler = options.onRestartRequiredChange" in settings_panel
    assert "Restart required." in settings_panel
    assert "Restart failed." in settings_panel
    assert "Restart unavailable." in settings_panel
    assert "restartRequired = true" in settings_panel
    assert "restartRequired = false" in settings_panel
    assert "await restartHandler()" in settings_panel
    assert "await loadSettings(activeContainer)" in settings_panel
    assert "saveButton.hidden = restartRequired" in settings_panel
    assert "closeButton.hidden = restartRequired" in settings_panel
    assert "restartButton.hidden = !restartRequired" in settings_panel
    assert "innerHTML" not in settings_panel


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


def test_desktop_can_render_optional_tool_calls_metadata() -> None:
    main_js = _read("desktop/src/main.js")
    assert "appendToolCalls" in main_js
    assert "Tool used:" in main_js
    assert "response.tool_calls" in main_js


def test_j1_readiness_components_and_containers_exist() -> None:
    index_html = _read("desktop/src/index.html")
    main_js = _read("desktop/src/main.js")
    readiness_panel = _read("desktop/src/components/readiness-panel.js")
    degraded_list = _read("desktop/src/components/degraded-list.js")

    assert 'id="readiness-panel"' in index_html
    assert 'id="degraded-conditions"' in index_html
    assert "./components/readiness-panel.js" in main_js
    assert "./components/degraded-list.js" in main_js
    assert "export function renderReadiness" in readiness_panel
    assert "export function renderDegradedList" in degraded_list
    assert "renderReadinessPanel(readiness, readinessEl)" in main_js
    assert "renderDegradedList(readiness, degradedEl)" in main_js
    assert 'invoke("get_readiness")' in main_js


def test_j1_voice_debug_is_collapsed_details_without_voice_capture_change() -> None:
    index_html = _read("desktop/src/index.html")
    main_js = _read("desktop/src/main.js")

    assert "<details" in index_html
    assert "<summary>Voice debug details</summary>" in index_html
    assert 'id="voice-detail"' in index_html
    assert index_html.index("<details") < index_html.index('id="voice-detail"')
    assert 'pttButton.addEventListener("click"' in main_js
    assert 'pttButton.addEventListener("pointerdown"' not in main_js
    assert 'pttButton.addEventListener("pointerup"' not in main_js
    assert 'pttButton.addEventListener("pointercancel"' not in main_js


def test_j3b_ptt_button_uses_click_start_click_stop_contract() -> None:
    index_html = _read("desktop/src/index.html")
    main_js = _read("desktop/src/main.js")

    assert 'id="ptt-button"' in index_html
    assert 'aria-pressed="false"' in index_html
    assert 'data-capture-state="idle"' in index_html
    assert "Hold to Talk" not in index_html
    assert "Hold to Talk" not in main_js
    assert 'pttButton.addEventListener("click"' in main_js
    assert 'pttButton.addEventListener("pointerdown"' not in main_js
    assert 'pttButton.addEventListener("pointerup"' not in main_js
    assert 'pttButton.addEventListener("pointercancel"' not in main_js
    assert "setCaptureState" in main_js
    for capture_state in ["idle", "recording", "processing"]:
        assert capture_state in main_js
    assert "Stop and Submit" in main_js
    assert "Start Voice" in main_js


def test_j3b_wake_indicator_component_renders_existing_wake_fields() -> None:
    index_html = _read("desktop/src/index.html")
    main_js = _read("desktop/src/main.js")
    wake_indicator = _read("desktop/src/components/wake-indicator.js")

    assert 'id="wake-indicator"' in index_html
    assert "./components/wake-indicator.js" in main_js
    assert "renderWakeStatus" in main_js
    assert "export function renderWakeStatus" in wake_indicator
    assert "textContent" in wake_indicator
    assert "innerHTML" not in wake_indicator
    for field in ["provider", "available", "monitoring", "reason"]:
        assert field in wake_indicator


def test_j1_readiness_payload_values_are_rendered_with_dom_text_apis() -> None:
    readiness_panel = _read("desktop/src/components/readiness-panel.js")
    degraded_list = _read("desktop/src/components/degraded-list.js")
    main_js = _read("desktop/src/main.js")

    assert "textContent" in readiness_panel
    assert "textContent" in degraded_list
    assert "innerHTML" not in readiness_panel
    assert "innerHTML" not in degraded_list
    assert "document.body.dataset.degraded" in main_js


def test_j1_llm_ollama_local_runtime_unavailable_is_degraded_not_failed() -> None:
    readiness_panel = _read("desktop/src/components/readiness-panel.js")
    degraded_list = _read("desktop/src/components/degraded-list.js")

    assert "isOllamaLocalRuntimeFallback" in readiness_panel
    assert "active_llm_runtime" in readiness_panel
    assert 'family?.family === "llm"' in readiness_panel
    assert 'toLowerCase() === "ollama"' in readiness_panel
    assert 'toLowerCase() === "local runtime unavailable"' in readiness_panel
    assert "return \"degraded\";" in readiness_panel
    assert "FAILED_REASON_TOKENS" in readiness_panel
    assert "local runtime unavailable" in readiness_panel
    assert "local runtime unavailable" not in degraded_list


def test_j2_state_label_component_exports_mapping_and_preserves_data_state() -> None:
    state_label = _read("desktop/src/components/state-label.js")

    assert "export function setStateLabel" in state_label
    assert "dataset.state" in state_label
    for state_key in [
        "BOOTSTRAP",
        "STARTING",
        "READY",
        "IDLE",
        "LISTENING",
        "TRANSCRIBING",
        "REASONING",
        "ACTING",
        "RESPONDING",
        "SPEAKING",
        "INTERRUPTED",
        "RECOVERING",
        "DEGRADED",
        "FAILED",
    ]:
        assert state_key in state_label
    for label in ["Starting", "Ready", "Listening", "Thinking", "Speaking", "Failed"]:
        assert label in state_label


def test_j2_main_state_displays_flow_through_state_label_helper() -> None:
    main_js = _read("desktop/src/main.js")

    assert "./components/state-label.js" in main_js
    assert "function setState(value, degraded = false)" in main_js
    assert "setStateLabel(value, stateEl)" in main_js
    assert "document.body.dataset.degraded" in main_js
    assert "turnStateEl.textContent =" not in main_js
    assert "stateEl.textContent =" not in main_js
    assert "setStateLabel(response.final_state, turnStateEl)" in main_js
    assert 'setStateLabel("REASONING", turnStateEl)' in main_js
    assert 'setStateLabel("FAILED", turnStateEl)' in main_js


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


def test_j4_style_tokens_are_defined_in_single_token_section() -> None:
    style_css = _read("desktop/src/style.css")

    assert style_css.count("JARVIS_V7_TOKENS_START") == 1
    assert style_css.count("JARVIS_V7_TOKENS_END") == 1
    assert style_css.index("JARVIS_V7_TOKENS_START") < style_css.index("JARVIS_V7_TOKENS_END")
    for token in [
        "--color-bg-base",
        "--color-accent",
        "--color-ready",
        "--color-degraded",
        "--color-failed",
        "--color-capture",
        "--color-text-primary",
        "--space-1",
    ]:
        assert token in style_css


def test_j4_style_rules_do_not_use_raw_color_values_outside_tokens() -> None:
    outside_tokens = _css_outside_token_section()

    assert re.search(r"#[0-9a-fA-F]{3,8}\b", outside_tokens) is None
    assert "rgb(" not in outside_tokens
    assert "rgba(" not in outside_tokens
    assert "hsl(" not in outside_tokens
    assert "hsla(" not in outside_tokens


def test_j4_state_capture_and_readiness_selectors_exist() -> None:
    style_css = _read("desktop/src/style.css")

    for selector in [
        '[data-state="LISTENING"]',
        '[data-state="REASONING"]',
        '[data-state="SPEAKING"]',
        '[data-state="DEGRADED"]',
        '[data-state="FAILED"]',
        '[data-capture-state="recording"]',
        '[data-capture-state="processing"]',
        'data-readiness-state="ready"',
        'data-readiness-state="degraded"',
        'data-readiness-state="failed"',
        ".degraded-condition",
        "capture-pulse",
    ]:
        assert selector in style_css


def test_j4_conversation_role_hierarchy_and_no_inline_styles() -> None:
    style_css = _read("desktop/src/style.css")
    index_html = _read("desktop/src/index.html")

    for selector in [
        ".message.user",
        ".message.assistant",
        ".message.system",
        ".message.presence",
    ]:
        assert selector in style_css
    assert " style=" not in index_html






