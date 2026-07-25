mod backend;

use backend::{
    close_session, confirm_memory as backend_confirm_memory,
    correct_memory as backend_correct_memory, create_session,
    dispute_memory as backend_dispute_memory, drain_memory_curation,
    forget_memory as backend_forget_memory, get_desktop_status as backend_desktop_status, get_json,
    get_memory_curation_status as backend_memory_curation_status,
    get_memory_detail as backend_memory_detail, get_memory_policy as backend_memory_policy,
    get_operator_config as backend_operator_config,
    get_personality_list as backend_personality_list,
    get_resident_voice_status as backend_resident_voice_status,
    get_session_status as backend_session_status, get_wake_status as backend_wake_status,
    invoke_resident_ptt as backend_invoke_resident_ptt, list_memories as backend_list_memories,
    select_personality as backend_select_personality,
    set_resident_voice_mode as backend_set_resident_voice_mode,
    set_resident_voice_tts_voice as backend_set_resident_voice_tts_voice,
    start_resident_voice_stream as backend_start_resident_voice_stream,
    start_wake_monitor as backend_start_wake_monitor,
    stop_resident_voice_stream as backend_stop_resident_voice_stream,
    stop_wake_monitor as backend_stop_wake_monitor, submit_text_turn,
    toggle_wake_monitor as backend_toggle_wake_monitor,
    update_memory_policy as backend_update_memory_policy, wait_healthy,
    write_operator_config as backend_write_operator_config, BackendProcessManager,
};
use reqwest::blocking::Client;
use serde_json::{json, Value};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Manager, State,
};

struct DesktopState {
    backend: Arc<Mutex<BackendProcessManager>>,
    http_client: Client,
    session_id: Arc<Mutex<Option<String>>>,
}

fn backend_base_url(state: &DesktopState) -> Result<String, String> {
    let manager = state
        .backend
        .lock()
        .map_err(|_| "backend manager lock poisoned".to_string())?;
    Ok(manager.base_url())
}

#[tauri::command]
fn start_backend(state: State<'_, DesktopState>) -> Result<String, String> {
    let (base_url, diagnostics) = {
        let mut manager = state
            .backend
            .lock()
            .map_err(|_| "backend manager lock poisoned".to_string())?;
        let diagnostics = match manager.spawn_backend() {
            Ok(diagnostics) => diagnostics,
            Err(err) => return Err(manager.startup_failure_payload(&err)),
        };
        (manager.base_url(), diagnostics)
    };

    if let Err(err) = wait_healthy(
        &state.http_client,
        &base_url,
        Duration::from_secs(90),
        || {
            let mut manager = state
                .backend
                .lock()
                .map_err(|_| "backend manager lock poisoned".to_string())?;
            manager.exited_status()
        },
    ) {
        let manager = state
            .backend
            .lock()
            .map_err(|_| "backend manager lock poisoned".to_string())?;
        return Err(manager.startup_failure_payload(&err));
    }

    let session = create_session(&state.http_client, &base_url)?;
    {
        let mut active_session = state
            .session_id
            .lock()
            .map_err(|_| "session lock poisoned".to_string())?;
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
        let mut active_session = state
            .session_id
            .lock()
            .map_err(|_| "session lock poisoned".to_string())?;
        active_session.take()
    };
    run_shutdown_sequence(
        || {
            if let Some(session_id) = session {
                close_session(&state.http_client, &base_url, &session_id)
            } else {
                Ok(())
            }
        },
        || drain_memory_curation(&state.http_client, &base_url),
        || {
            let mut manager = state
                .backend
                .lock()
                .map_err(|_| "backend manager lock poisoned".to_string())?;
            manager.kill_backend();
            Ok(())
        },
    )
}

fn run_shutdown_sequence<C, D, K>(close: C, drain: D, kill: K) -> Result<(), String>
where
    C: FnOnce() -> Result<(), String>,
    D: FnOnce() -> Result<(), String>,
    K: FnOnce() -> Result<(), String>,
{
    let _ = close();
    let _ = drain();
    kill()
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
fn get_desktop_status(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_desktop_status(&state.http_client, &base_url)
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
fn set_resident_voice_tts_voice(
    voice: String,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
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
fn select_personality(
    profile_id: String,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
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

fn required_memory_id(fact_id: String) -> Result<String, String> {
    let trimmed = fact_id.trim();
    if trimmed.is_empty() {
        return Err("memory fact_id is empty".to_string());
    }
    Ok(trimmed.to_string())
}

fn required_memory_text(text: String) -> Result<String, String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Err("memory replacement_text is empty".to_string());
    }
    Ok(trimmed.to_string())
}

fn expected_memory_revision(expected_revision: u64) -> Result<u64, String> {
    if expected_revision == 0 {
        return Err("memory expected_revision must be positive".to_string());
    }
    Ok(expected_revision)
}

fn optional_trimmed(value: Option<String>) -> Option<String> {
    value.and_then(|item| {
        let trimmed = item.trim();
        (!trimmed.is_empty()).then(|| trimmed.to_string())
    })
}

#[tauri::command]
fn get_memory_policy(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_memory_policy(&state.http_client, &base_url)
}

#[tauri::command]
fn update_memory_policy(
    automatic_curation_enabled: bool,
    expected_revision: u64,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_update_memory_policy(
        &state.http_client,
        &base_url,
        automatic_curation_enabled,
        expected_memory_revision(expected_revision)?,
    )
}

#[tauri::command]
fn list_memories(
    lifecycle_state: Option<String>,
    kind: Option<String>,
    query: Option<String>,
    offset: Option<u32>,
    limit: Option<u32>,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    let lifecycle_state = optional_trimmed(lifecycle_state);
    let kind = optional_trimmed(kind);
    let query = optional_trimmed(query);
    backend_list_memories(
        &state.http_client,
        &base_url,
        lifecycle_state.as_deref(),
        kind.as_deref(),
        query.as_deref(),
        offset.unwrap_or(0),
        limit.unwrap_or(20),
    )
}

#[tauri::command]
fn get_memory_detail(fact_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_memory_detail(&state.http_client, &base_url, &required_memory_id(fact_id)?)
}

#[tauri::command]
fn confirm_memory(
    fact_id: String,
    expected_revision: u64,
    reason: Option<String>,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    let fact_id = required_memory_id(fact_id)?;
    let reason = optional_trimmed(reason);
    backend_confirm_memory(
        &state.http_client,
        &base_url,
        &fact_id,
        expected_memory_revision(expected_revision)?,
        reason.as_deref(),
    )
}

#[tauri::command]
fn correct_memory(
    fact_id: String,
    expected_revision: u64,
    replacement_text: String,
    replacement_value: Option<String>,
    reason: Option<String>,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    let fact_id = required_memory_id(fact_id)?;
    let replacement_text = required_memory_text(replacement_text)?;
    let replacement_value = optional_trimmed(replacement_value);
    let reason = optional_trimmed(reason);
    backend_correct_memory(
        &state.http_client,
        &base_url,
        &fact_id,
        expected_memory_revision(expected_revision)?,
        &replacement_text,
        replacement_value.as_deref(),
        reason.as_deref(),
    )
}

#[tauri::command]
fn dispute_memory(
    fact_id: String,
    expected_revision: u64,
    reason: Option<String>,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    let fact_id = required_memory_id(fact_id)?;
    let reason = optional_trimmed(reason);
    backend_dispute_memory(
        &state.http_client,
        &base_url,
        &fact_id,
        expected_memory_revision(expected_revision)?,
        reason.as_deref(),
    )
}

#[tauri::command]
fn forget_memory(
    fact_id: String,
    expected_revision: u64,
    reason: Option<String>,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    let fact_id = required_memory_id(fact_id)?;
    let reason = optional_trimmed(reason);
    backend_forget_memory(
        &state.http_client,
        &base_url,
        &fact_id,
        expected_memory_revision(expected_revision)?,
        reason.as_deref(),
    )
}

#[tauri::command]
fn get_memory_curation_status(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_memory_curation_status(&state.http_client, &base_url)
}

#[tauri::command]
fn submit_text(text: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return Err("text input is empty".to_string());
    }
    let base_url = backend_base_url(&state)?;
    let session_id = state
        .session_id
        .lock()
        .map_err(|_| "session lock poisoned".to_string())?
        .clone();
    submit_text_turn(
        &state.http_client,
        &base_url,
        trimmed,
        session_id.as_deref(),
    )
}

fn setup_tray(app: &tauri::App) -> tauri::Result<()> {
    let start = MenuItem::with_id(app, "start_backend", "Start Backend", true, None::<&str>)?;
    let stop = MenuItem::with_id(app, "stop_backend", "Stop Backend", true, None::<&str>)?;
    let show = MenuItem::with_id(app, "show_window", "Show Window", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Quit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&start, &stop, &show, &quit])?;
    let icon = app
        .default_window_icon()
        .expect("default window icon missing")
        .clone();

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
    let backend =
        BackendProcessManager::new().expect("failed to initialize backend process manager");
    let http_client = Client::builder()
        .build()
        .expect("failed to initialize desktop HTTP client");
    tauri::Builder::default()
        .manage(DesktopState {
            backend: Arc::new(Mutex::new(backend)),
            http_client,
            session_id: Arc::new(Mutex::new(None)),
        })
        .invoke_handler(tauri::generate_handler![
            start_backend,
            stop_backend,
            health_check,
            get_readiness,
            get_session_status,
            get_desktop_status,
            invoke_resident_ptt,
            get_wake_status,
            start_wake_monitor,
            stop_wake_monitor,
            toggle_wake_monitor,
            get_personality_list,
            select_personality,
            get_operator_config,
            write_operator_config,
            get_memory_policy,
            update_memory_policy,
            list_memories,
            get_memory_detail,
            confirm_memory,
            correct_memory,
            dispute_memory,
            forget_memory,
            get_memory_curation_status,
            get_resident_voice_status,
            start_resident_voice_stream,
            stop_resident_voice_stream,
            set_resident_voice_mode,
            set_resident_voice_tts_voice,
            submit_text
        ])
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

#[cfg(test)]
mod shutdown_tests {
    use super::run_shutdown_sequence;
    use std::cell::RefCell;

    #[test]
    fn stop_order_is_close_then_drain_then_kill_even_on_request_errors() {
        let events = RefCell::new(Vec::new());

        run_shutdown_sequence(
            || {
                events.borrow_mut().push("close");
                Err("close timeout".to_string())
            },
            || {
                events.borrow_mut().push("drain");
                Err("drain timeout".to_string())
            },
            || {
                events.borrow_mut().push("kill");
                Ok(())
            },
        )
        .expect("kill remains reachable");

        assert_eq!(events.into_inner(), vec!["close", "drain", "kill"]);
    }
}
