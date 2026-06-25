mod backend;

use backend::{close_session, create_session, get_json, get_operator_config as backend_operator_config, get_personality_list as backend_personality_list, get_resident_voice_status as backend_resident_voice_status, get_session_status as backend_session_status, get_wake_status as backend_wake_status, invoke_resident_ptt as backend_invoke_resident_ptt, select_personality as backend_select_personality, start_wake_monitor as backend_start_wake_monitor, stop_wake_monitor as backend_stop_wake_monitor, submit_text_turn, toggle_wake_monitor as backend_toggle_wake_monitor, wait_healthy, write_operator_config as backend_write_operator_config, BackendProcessManager};
use serde_json::{json, Value};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{menu::{Menu, MenuItem}, tray::TrayIconBuilder, Manager, State};

struct DesktopState {
    backend: Arc<Mutex<BackendProcessManager>>,
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
        let diagnostics = manager.spawn_backend()?;
        (manager.base_url(), diagnostics)
    };

    wait_healthy(&base_url, Duration::from_secs(30), || {
        let mut manager = state.backend.lock().map_err(|_| "backend manager lock poisoned".to_string())?;
        manager.exited_status()
    })
    .map_err(|err| format!("{err}\nstartup diagnostics: {}", serde_json::to_string_pretty(&diagnostics).unwrap_or_default()))?;

    let session = create_session(&base_url)?;
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
        let _ = close_session(&base_url, &session_id);
    }
    let mut manager = state.backend.lock().map_err(|_| "backend manager lock poisoned".to_string())?;
    manager.kill_backend();
    Ok(())
}

#[tauri::command]
fn health_check(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    match get_json(&base_url, "/health") {
        Ok(body) => Ok(body),
        Err(error) => Ok(json!({"status": "error", "error": error}).to_string()),
    }
}

#[tauri::command]
fn get_readiness(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    get_json(&base_url, "/readiness")
}

#[tauri::command]
fn get_session_status(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_session_status(&base_url)
}

#[tauri::command]
fn invoke_resident_ptt(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_invoke_resident_ptt(&base_url)
}

#[tauri::command]
fn get_wake_status(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_wake_status(&base_url)
}

#[tauri::command]
fn get_resident_voice_status(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_resident_voice_status(&base_url)
}

#[tauri::command]
fn start_wake_monitor(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_start_wake_monitor(&base_url)
}

#[tauri::command]
fn stop_wake_monitor(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_stop_wake_monitor(&base_url)
}

#[tauri::command]
fn toggle_wake_monitor(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_toggle_wake_monitor(&base_url)
}

#[tauri::command]
fn get_personality_list(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_personality_list(&base_url)
}

#[tauri::command]
fn select_personality(profile_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let trimmed = profile_id.trim();
    if trimmed.is_empty() {
        return Err("personality profile_id is empty".to_string());
    }
    let base_url = backend_base_url(&state)?;
    backend_select_personality(&base_url, trimmed)
}

#[tauri::command]
fn get_operator_config(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_operator_config(&base_url)
}

#[tauri::command]
fn write_operator_config(fields: Value, state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_write_operator_config(&base_url, fields)
}

#[tauri::command]
fn submit_text(text: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Err("text input is empty".to_string());
    }
    let base_url = backend_base_url(&state)?;
    let session_id = state.session_id.lock().map_err(|_| "session lock poisoned".to_string())?.clone();
    submit_text_turn(&base_url, trimmed, session_id.as_deref())
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
    tauri::Builder::default()
        .manage(DesktopState { backend: Arc::new(Mutex::new(backend)), session_id: Arc::new(Mutex::new(None)) })
        .invoke_handler(tauri::generate_handler![start_backend, stop_backend, health_check, get_readiness, get_session_status, invoke_resident_ptt, get_wake_status, start_wake_monitor, stop_wake_monitor, toggle_wake_monitor, get_personality_list, select_personality, get_operator_config, write_operator_config, get_resident_voice_status, submit_text])
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
