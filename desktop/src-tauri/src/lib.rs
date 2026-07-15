mod backend;

use backend::{close_session, create_session, get_json, get_operator_config as backend_operator_config, get_personality_list as backend_personality_list, get_resident_voice_status as backend_resident_voice_status, get_session_status as backend_session_status, get_wake_status as backend_wake_status, invoke_resident_ptt as backend_invoke_resident_ptt, select_personality as backend_select_personality, set_resident_voice_mode as backend_set_resident_voice_mode, set_resident_voice_tts_voice as backend_set_resident_voice_tts_voice, start_resident_voice_stream as backend_start_resident_voice_stream, start_wake_monitor as backend_start_wake_monitor, stop_resident_voice_stream as backend_stop_resident_voice_stream, stop_wake_monitor as backend_stop_wake_monitor, submit_text_turn, toggle_wake_monitor as backend_toggle_wake_monitor, wait_healthy, write_operator_config as backend_write_operator_config, BackendProcessManager};
use reqwest::blocking::Client;
use serde_json::{json, Value};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{menu::{Menu, MenuItem}, tray::TrayIconBuilder, Manager, State};

struct DesktopState {
    backend: Arc<Mutex<BackendProcessManager>>,
    http_client: Client,
    session_id: Arc<Mutex<Option<String>>>,
}

fn backend_base_url(state: &DesktopState) -> Result<String, String> {
    let manager = state.backend.lock().map_err(|_| "backend manager lock poisoned".to_string())?;
    Ok(manager.base_url())
}

#[tauri::command]
fn start_backend(state: State<'_, DesktopState>) -> Result<String, String> {
    let (base_url, diagnostics) = {
        let mut manager = state.backend.lock().map_err(|_| "backend manager lock poisoned".to_string())?;
        let diagnostics = match manager.spawn_backend() {
            Ok(diagnostics) => diagnostics,
            Err(err) => return Err(manager.startup_failure_payload(&err)),
        };
        (manager.base_url(), diagnostics)
    };

    if let Err(err) = wait_healthy(&state.http_client, &base_url, Duration::from_secs(90), || {
        let mut manager = state.backend.lock().map_err(|_| "backend manager lock poisoned".to_string())?;
        manager.exited_status()
    }) {
        let manager = state.backend.lock().map_err(|_| "backend manager lock poisoned".to_string())?;
        return Err(manager.startup_failure_payload(&err));
    }

    let session = create_session(&state.http_client, &base_url)?;
    {
        let mut active_session = state.session_id.lock().map_err(|_| "session lock poisoned".to_string())?;
        *active_session = Some(session.session_id.clone());
    }

    serde_json::to_string(&json!({
        "status": "ok",
        "session_id": session.session_id,
        "state": session.state,
        "turn_count": session.turn_count,
        "diagnostics": diagnostics
    }))
    .map_err(|err| format!("failed to serialize start_backend response: {err}"))
}

#[tauri::command]
fn stop_backend(state: State<'_, DesktopState>) -> Result<(), String> {
    let base_url = backend_base_url(&state)?;
    let session = {
        let mut active_session = state.session_id.lock().map_err(|_| "session lock poisoned".to_string())?;
        active_session.take()
    };
    if let Some(session_id) = session {
        let _ = close_session(&state.http_client, &base_url, &session_id);
    }
    let mut manager = state.backend.lock().map_err(|_| "backend manager lock poisoned".to_string())?;
    manager.kill_backend();
    Ok(())
}

#[tauri::command]
fn health_check(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    match get_json(&state.http_client, &base_url, "/health") {
        Ok(body) => Ok(body),
        Err(error) => Ok(json!({"status": "error", "error": error}).to_string()),
    }
}

#[tauri::command]
fn get_readiness(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    get_json(&state.http_client, &base_url, "/readiness")
}

#[tauri::command]
fn get_session_status(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_session_status(&state.http_client, &base_url)
}

#[tauri::command]
fn invoke_resident_ptt(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_invoke_resident_ptt(&state.http_client, &base_url)
}

#[tauri::command]
fn get_wake_status(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_wake_status(&state.http_client, &base_url)
}

#[tauri::command]
fn get_resident_voice_status(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_resident_voice_status(&state.http_client, &base_url)
}

#[tauri::command]
fn start_resident_voice_stream(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_start_resident_voice_stream(&state.http_client, &base_url)
}

#[tauri::command]
fn stop_resident_voice_stream(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_stop_resident_voice_stream(&state.http_client, &base_url)
}

#[tauri::command]
fn set_resident_voice_mode(mode: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let trimmed = mode.trim();
    if trimmed.is_empty() {
        return Err("resident voice mode is empty".to_string());
    }
    let base_url = backend_base_url(&state)?;
    backend_set_resident_voice_mode(&state.http_client, &base_url, trimmed)
}

#[tauri::command]
fn set_resident_voice_tts_voice(voice: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let trimmed = voice.trim();
    if trimmed.is_empty() {
        return Err("resident voice tts voice is empty".to_string());
    }
    let base_url = backend_base_url(&state)?;
    backend_set_resident_voice_tts_voice(&state.http_client, &base_url, trimmed)
}

#[tauri::command]
fn start_wake_monitor(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_start_wake_monitor(&state.http_client, &base_url)
}

#[tauri::command]
fn stop_wake_monitor(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_stop_wake_monitor(&state.http_client, &base_url)
}

#[tauri::command]
fn toggle_wake_monitor(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_toggle_wake_monitor(&state.http_client, &base_url)
}

#[tauri::command]
fn get_personality_list(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_personality_list(&state.http_client, &base_url)
}

#[tauri::command]
fn select_personality(profile_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let trimmed = profile_id.trim();
    if trimmed.is_empty() {
        return Err("personality profile_id is empty".to_string());
    }
    let base_url = backend_base_url(&state)?;
    backend_select_personality(&state.http_client, &base_url, trimmed)
}

#[tauri::command]
fn get_operator_config(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_operator_config(&state.http_client, &base_url)
}

#[tauri::command]
fn write_operator_config(fields: Value, state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_write_operator_config(&state.http_client, &base_url, fields)
}

#[tauri::command]
fn submit_text(text: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Err("text input is empty".to_string());
    }
    let base_url = backend_base_url(&state)?;
    let session_id = state.session_id.lock().map_err(|_| "session lock poisoned".to_string())?.clone();
    submit_text_turn(&state.http_client, &base_url, trimmed, session_id.as_deref())
}

fn setup_tray(app: &tauri::App) -> tauri::Result<()> {
    let start = MenuItem::with_id(app, "start_backend", "Start Backend", true, None::<&str>)?;
    let stop = MenuItem::with_id(app, "stop_backend", "Stop Backend", true, None::<&str>)?;
    let show = MenuItem::with_id(app, "show_window", "Show Window", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&start, &stop, &show, &quit])?;
    let icon = app.default_window_icon().expect("default window icon missing").clone();

    TrayIconBuilder::new()
        .icon(icon)
        .menu(&menu)
        .show_menu_on_left_click(true)
        .on_menu_event(|app, event| match event.id.as_ref() {
            "start_backend" => {
                let state = app.state::<DesktopState>();
                let _ = start_backend(state);
            }
            "stop_backend" => {
                let state = app.state::<DesktopState>();
                let _ = stop_backend(state);
            }
            "show_window" => {
                if let Some(window) = app.get_webview_window("main") {
                    let _ = window.unminimize();
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }
            "quit" => {
                let state = app.state::<DesktopState>();
                let _ = stop_backend(state);
                app.exit(0);
            }
            _ => {}
        })
        .build(app)?;

    Ok(())
}

pub fn run() {
    let backend = BackendProcessManager::new().expect("failed to initialize backend process manager");
    let http_client = Client::builder().build().expect("failed to initialize desktop HTTP client");
    tauri::Builder::default()
        .manage(DesktopState { backend: Arc::new(Mutex::new(backend)), http_client, session_id: Arc::new(Mutex::new(None)) })
        .invoke_handler(tauri::generate_handler![start_backend, stop_backend, health_check, get_readiness, get_session_status, invoke_resident_ptt, get_wake_status, start_wake_monitor, stop_wake_monitor, toggle_wake_monitor, get_personality_list, select_personality, get_operator_config, write_operator_config, get_resident_voice_status, start_resident_voice_stream, stop_resident_voice_stream, set_resident_voice_mode, set_resident_voice_tts_voice, submit_text])
        .setup(|app| {
            setup_tray(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::CloseRequested { .. }) {
                if let Some(state) = window.try_state::<DesktopState>() {
                    let _ = stop_backend(state);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running JARVISv7 desktop host");
}
