mod backend;

use backend::{
    cancel_action as backend_cancel_action, close_session,
    confirm_memory as backend_confirm_memory,
    correct_memory as backend_correct_memory, create_session,
    decide_action as backend_decide_action,
    create_llm_profile as backend_create_llm_profile,
    delete_llm_profile as backend_delete_llm_profile,
    dispute_memory as backend_dispute_memory, drain_memory_curation,
    forget_memory as backend_forget_memory,
    get_action_audit as backend_action_audit,
    get_extension_body as backend_extension_body,
    get_extension_definition as backend_extension_definition,
    get_extension_detail as backend_extension_detail,
    get_extension_errors as backend_extension_errors,
    get_extension_runtime as backend_extension_runtime,
    get_extension_runs as backend_extension_runs,
    get_extensions as backend_extensions,
    get_action_capabilities as backend_action_capabilities,
    get_action_status as backend_action_status,
    get_artifact_retention_policy as backend_artifact_retention_policy,
    get_pending_actions as backend_pending_actions,
    invoke_extension as backend_invoke_extension,
    answer_extension_input as backend_answer_extension_input,
    write_extension_credential as backend_write_extension_credential,
    get_extension_oauth as backend_get_extension_oauth,
    start_extension_oauth as backend_start_extension_oauth,
    complete_extension_oauth as backend_complete_extension_oauth,
    forget_extension_oauth as backend_forget_extension_oauth,
    disconnect_extension as backend_disconnect_extension,
    list_agents as backend_list_agents,
    get_agent as backend_get_agent,
    invoke_agent as backend_invoke_agent,
    list_agent_runs as backend_list_agent_runs,
    cancel_agent as backend_cancel_agent,
    propose_action as backend_propose_action,
    set_extension_state as backend_set_extension_state,
    get_desktop_status as backend_desktop_status, get_json,
    get_memory_curation_status as backend_memory_curation_status,
    get_memory_detail as backend_memory_detail, get_memory_layers as backend_memory_layers,
    get_memory_policy as backend_memory_policy,
    get_llm_config as backend_llm_config,
    get_operator_config as backend_operator_config,
    get_personality_list as backend_personality_list,
    get_resident_voice_status as backend_resident_voice_status,
    get_session_status as backend_session_status, get_wake_status as backend_wake_status,
    invoke_resident_ptt as backend_invoke_resident_ptt, list_memories as backend_list_memories,
    rotate_secret_store_key as backend_rotate_secret_store_key,
    select_personality as backend_select_personality,
    set_resident_voice_mode as backend_set_resident_voice_mode,
    set_resident_voice_tts_voice as backend_set_resident_voice_tts_voice,
    start_resident_voice_stream as backend_start_resident_voice_stream,
    start_wake_monitor as backend_start_wake_monitor,
    stop_resident_voice_stream as backend_stop_resident_voice_stream,
    stop_wake_monitor as backend_stop_wake_monitor, submit_text_turn,
    test_llm_profile as backend_test_llm_profile,
    toggle_wake_monitor as backend_toggle_wake_monitor,
    update_llm_profile as backend_update_llm_profile,
    update_llm_selection as backend_update_llm_selection,
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
use tauri_plugin_opener::OpenerExt;

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
        let active_session = state
            .session_id
            .lock()
            .map_err(|_| "session lock poisoned".to_string())?;
        active_session.clone()
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
            manager.shutdown_or_kill(&state.http_client)
        },
    )?;
    *state.session_id.lock().map_err(|_| "session lock poisoned".to_string())? = None;
    Ok(())
}

fn run_shutdown_sequence<C, D, K>(close: C, drain: D, kill: K) -> Result<(), String>
where
    C: FnOnce() -> Result<(), String>,
    D: FnOnce() -> Result<(), String>,
    K: FnOnce() -> Result<(), String>,
{
    close()?;
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

fn required_profile_id(profile_id: String) -> Result<String, String> {
    let trimmed = profile_id.trim();
    if trimmed.is_empty() {
        return Err("LLM profile_id is empty".to_string());
    }
    Ok(trimmed.to_string())
}

#[tauri::command]
fn get_llm_config(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_llm_config(&state.http_client, &base_url)
}

#[tauri::command]
fn create_llm_profile(profile: Value, state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_create_llm_profile(&state.http_client, &base_url, profile)
}

#[tauri::command]
fn update_llm_profile(
    profile_id: String,
    profile: Value,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let profile_id = required_profile_id(profile_id)?;
    let base_url = backend_base_url(&state)?;
    backend_update_llm_profile(&state.http_client, &base_url, &profile_id, profile)
}

#[tauri::command]
fn delete_llm_profile(
    profile_id: String,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let profile_id = required_profile_id(profile_id)?;
    let base_url = backend_base_url(&state)?;
    backend_delete_llm_profile(&state.http_client, &base_url, &profile_id)
}

#[tauri::command]
fn test_llm_profile(profile_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let profile_id = required_profile_id(profile_id)?;
    let base_url = backend_base_url(&state)?;
    backend_test_llm_profile(&state.http_client, &base_url, &profile_id)
}

#[tauri::command]
fn update_llm_selection(
    selection: Value,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_update_llm_selection(&state.http_client, &base_url, selection)
}

#[tauri::command]
fn rotate_secret_store_key(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_rotate_secret_store_key(&state.http_client, &base_url)
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

fn required_extension_id(extension_id: String) -> Result<String, String> {
    let trimmed = extension_id.trim();
    if trimmed.is_empty() {
        return Err("extension_id is empty".to_string());
    }
    Ok(trimmed.to_string())
}

fn required_extension_state(state: String) -> Result<String, String> {
    match state.trim() {
        "enabled" => Ok("enabled".to_string()),
        "disabled" => Ok("disabled".to_string()),
        "retired" => Ok("retired".to_string()),
        _ => Err("extension state must be enabled, disabled, or retired".to_string()),
    }
}

fn required_proposal_id(proposal_id: String) -> Result<String, String> {
    let trimmed = proposal_id.trim();
    if trimmed.is_empty() {
        return Err("action proposal_id is empty".to_string());
    }
    Ok(trimmed.to_string())
}

fn required_action_outcome(outcome: String) -> Result<String, String> {
    match outcome.trim() {
        "approved" => Ok("approved".to_string()),
        "denied" => Ok("denied".to_string()),
        _ => Err("action outcome must be approved or denied".to_string()),
    }
}

fn required_action_reason(reason: String) -> Result<String, String> {
    let trimmed = reason.trim();
    if trimmed.is_empty() {
        return Err("action reason is empty".to_string());
    }
    Ok(trimmed.to_string())
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
fn get_memory_layers(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_memory_layers(&state.http_client, &base_url)
}

#[tauri::command]
fn get_artifact_retention_policy(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_artifact_retention_policy(&state.http_client, &base_url)
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
fn get_action_capabilities(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_action_capabilities(&state.http_client, &base_url)
}

#[tauri::command]
fn get_pending_actions(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_pending_actions(&state.http_client, &base_url)
}

#[tauri::command]
fn get_action_audit(limit: Option<u32>, state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_action_audit(&state.http_client, &base_url, limit.unwrap_or(20))
}

#[tauri::command]
fn propose_action(
    capability_id: String,
    arguments: Option<Value>,
    reason: String,
    proposed_by: Option<String>,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    let capability_id = required_proposal_id(capability_id)?;
    let reason = required_action_reason(reason)?;
    let proposed_by = optional_trimmed(proposed_by).unwrap_or_else(|| "operator".to_string());
    backend_propose_action(
        &state.http_client,
        &base_url,
        &capability_id,
        arguments.unwrap_or_else(|| json!({})),
        &reason,
        &proposed_by,
    )
}

#[tauri::command]
fn get_action_status(
    proposal_id: String,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_action_status(
        &state.http_client,
        &base_url,
        &required_proposal_id(proposal_id)?,
    )
}

#[tauri::command]
async fn decide_action(
    proposal_id: String,
    outcome: String,
    reason: Option<String>,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    let proposal_id = required_proposal_id(proposal_id)?;
    let outcome = required_action_outcome(outcome)?;
    let reason = optional_trimmed(reason);
    let client = state.http_client.clone();
    tauri::async_runtime::spawn_blocking(move || {
        backend_decide_action(&client, &base_url, &proposal_id, &outcome, reason.as_deref())
    }).await.map_err(|error| error.to_string())?
}

#[tauri::command]
fn get_extensions(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_extensions(&state.http_client, &base_url)
}

#[tauri::command]
fn get_extension_errors(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_extension_errors(&state.http_client, &base_url)
}

#[tauri::command]
fn get_extension_detail(
    extension_id: String,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_extension_detail(
        &state.http_client,
        &base_url,
        &required_extension_id(extension_id)?,
    )
}

#[tauri::command]
fn get_extension_body(
    extension_id: String,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_extension_body(
        &state.http_client,
        &base_url,
        &required_extension_id(extension_id)?,
    )
}

#[tauri::command]
fn get_extension_definition(
    extension_id: String,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_extension_definition(
        &state.http_client,
        &base_url,
        &required_extension_id(extension_id)?,
    )
}

#[tauri::command]
fn set_extension_state(
    extension_id: String,
    extension_state: String,
    expected_revision: Option<u64>,
    reason: Option<String>,
    state: State<'_, DesktopState>,
) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    let extension_id = required_extension_id(extension_id)?;
    let target = required_extension_state(extension_state)?;
    let reason = optional_trimmed(reason);
    backend_set_extension_state(
        &state.http_client,
        &base_url,
        &extension_id,
        &target,
        expected_revision,
        reason.as_deref(),
    )
}

#[tauri::command]
fn get_extension_runtime(extension_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    backend_extension_runtime(&state.http_client, &backend_base_url(&state)?, &required_extension_id(extension_id)?)
}

#[tauri::command]
fn get_extension_runs(state: State<'_, DesktopState>) -> Result<String, String> {
    backend_extension_runs(&state.http_client, &backend_base_url(&state)?)
}

#[tauri::command]
async fn invoke_extension(extension_id: String, capability_id: String, action_arguments: Value, state: State<'_, DesktopState>) -> Result<String, String> {
    // Operator invocation now executes the capability synchronously on the backend
    // instead of just parking it (ADR 0005) - a long-running tool call or one that waits
    // on elicitation can hold this call open for as long as the operator takes to
    // answer. A plain synchronous command would block Tauri's shared blocking thread
    // pool for that whole duration, starving other commands (polling extension runs,
    // answering the elicitation itself, cancelling) queued behind it on that pool - the
    // same reason `decide_action` already moved its own backend call onto
    // `spawn_blocking` under an `async fn`.
    let base_url = backend_base_url(&state)?;
    let extension_id = required_extension_id(extension_id)?;
    let capability_id = required_extension_id(capability_id)?;
    let client = state.http_client.clone();
    tauri::async_runtime::spawn_blocking(move || {
        backend_invoke_extension(&client, &base_url, &extension_id, &capability_id, action_arguments)
    }).await.map_err(|error| error.to_string())?
}

#[tauri::command]
fn answer_extension_input(run_id: String, request_id: String, answer: Value, state: State<'_, DesktopState>) -> Result<String, String> {
    backend_answer_extension_input(&state.http_client, &backend_base_url(&state)?, &required_extension_id(run_id)?, &required_extension_id(request_id)?, answer)
}

#[tauri::command]
fn write_extension_credential(extension_id: String, name: String, secret: String, state: State<'_, DesktopState>) -> Result<String, String> {
    if name.trim().is_empty() || secret.is_empty() { return Err("credential name and secret are required".to_string()); }
    backend_write_extension_credential(&state.http_client, &backend_base_url(&state)?, &required_extension_id(extension_id)?, name.trim(), &secret)
}

#[tauri::command]
fn get_extension_oauth(extension_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    backend_get_extension_oauth(&state.http_client, &backend_base_url(&state)?, &required_extension_id(extension_id)?)
}

#[tauri::command]
fn start_extension_oauth(extension_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    backend_start_extension_oauth(&state.http_client, &backend_base_url(&state)?, &required_extension_id(extension_id)?)
}

#[tauri::command]
fn complete_extension_oauth(extension_id: String, code: String, oauth_state: String, state: State<'_, DesktopState>) -> Result<String, String> {
    if code.trim().is_empty() || oauth_state.trim().is_empty() {
        return Err("authorization code and state are required".to_string());
    }
    backend_complete_extension_oauth(&state.http_client, &backend_base_url(&state)?, &required_extension_id(extension_id)?, code.trim(), oauth_state.trim())
}

#[tauri::command]
fn forget_extension_oauth(extension_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    backend_forget_extension_oauth(&state.http_client, &backend_base_url(&state)?, &required_extension_id(extension_id)?)
}

#[tauri::command]
fn disconnect_extension(extension_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    backend_disconnect_extension(&state.http_client, &backend_base_url(&state)?, &required_extension_id(extension_id)?)
}

#[tauri::command]
fn list_agents(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_list_agents(&state.http_client, &base_url)
}

#[tauri::command]
fn get_agent(profile_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_get_agent(&state.http_client, &base_url, &profile_id)
}

#[tauri::command]
fn invoke_agent(profile_id: String, prompt: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_invoke_agent(&state.http_client, &base_url, &profile_id, &prompt)
}

#[tauri::command]
fn list_agent_runs(state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_list_agent_runs(&state.http_client, &base_url)
}

#[tauri::command]
fn cancel_agent(profile_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_cancel_agent(&state.http_client, &base_url, &profile_id)
}

#[tauri::command]
fn cancel_action(proposal_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    backend_cancel_action(
        &state.http_client,
        &base_url,
        &required_proposal_id(proposal_id)?,
    )
}

#[tauri::command]
async fn submit_text(text: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let trimmed = text.trim().to_owned();
    if trimmed.is_empty() {
        return Err("text input is empty".to_string());
    }
    let base_url = backend_base_url(&state)?;
    let session_id = state
        .session_id
        .lock()
        .map_err(|_| "session lock poisoned".to_string())?
        .clone();
    let client = state.http_client.clone();
    tauri::async_runtime::spawn_blocking(move || {
        submit_text_turn(&client, &base_url, &trimmed, session_id.as_deref())
    }).await.map_err(|error| error.to_string())?
}

#[tauri::command]
async fn cancel_search(session_id: String, turn_id: String, state: State<'_, DesktopState>) -> Result<String, String> {
    let base_url = backend_base_url(&state)?;
    let client = state.http_client.clone();
    tauri::async_runtime::spawn_blocking(move || {
        backend::cancel_search(&client, &base_url, &session_id, &turn_id)
    }).await.map_err(|error| error.to_string())?
}

fn public_source_url(value: &str) -> Result<String, String> {
    if value.len() > 4096 || value.chars().any(|c| c.is_control() || c.is_whitespace() || c == '\\') {
        return Err("invalid source URL".into());
    }
    let url = reqwest::Url::parse(value).map_err(|_| "invalid source URL".to_string())?;
    if !matches!(url.scheme(), "http" | "https") || !url.username().is_empty() || url.password().is_some()
        || url.port().is_some() {
        return Err("public HTTP(S) source required".into());
    }
    let host = url.host_str().ok_or("missing source hostname")?.trim_end_matches('.');
    let ip_host = host.trim_start_matches('[').trim_end_matches(']');
    let public = match ip_host.parse::<std::net::IpAddr>() {
        Ok(std::net::IpAddr::V4(ip)) => {
            let [a, b, c, _] = ip.octets();
            !ip.is_private() && !ip.is_loopback() && !ip.is_link_local() && !ip.is_documentation()
                && !ip.is_broadcast() && !ip.is_multicast() && a != 0 && a < 240
                && !(a == 100 && (64..=127).contains(&b)) && !(a == 192 && b == 0 && c == 0)
                && !(a == 198 && (b == 18 || b == 19))
        }
        Ok(std::net::IpAddr::V6(ip)) => {
            let s = ip.segments();
            (s[0] & 0xe000) == 0x2000 && s[0] != 0x2002
                && !(s[0] == 0x2001 && (s[1] < 0x200 || s[1] == 0xdb8))
        }
        Err(_) => host.contains('.') && ![".localhost", ".local", ".internal", ".home", ".lan"].iter().any(|suffix| host.ends_with(suffix)),
    };
    if !public { return Err("nonpublic source destination".into()); }
    Ok(url.to_string())
}

#[tauri::command]
fn open_search_source(url: String, app: tauri::AppHandle) -> Result<(), String> {
    let url = public_source_url(&url)?;
    app.opener().open_url(url, None::<&str>).map_err(|error| error.to_string())
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
                if stop_backend(state).is_ok() {
                    app.exit(0);
                }
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
        .plugin(tauri_plugin_opener::init())
        .manage(DesktopState {
            backend: Arc::new(Mutex::new(backend)),
            http_client,
            session_id: Arc::new(Mutex::new(None)),
        })
        .invoke_handler(tauri::generate_handler![
            cancel_search,
            open_search_source,
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
            get_llm_config,
            create_llm_profile,
            update_llm_profile,
            delete_llm_profile,
            test_llm_profile,
            update_llm_selection,
            rotate_secret_store_key,
            get_memory_policy,
            get_memory_layers,
            get_artifact_retention_policy,
            update_memory_policy,
            list_memories,
            get_memory_detail,
            confirm_memory,
            correct_memory,
            dispute_memory,
            forget_memory,
            get_memory_curation_status,
            get_action_capabilities,
            get_pending_actions,
            get_action_audit,
            propose_action,
            get_action_status,
            decide_action,
            cancel_action,
            get_extensions,
            get_extension_errors,
            get_extension_detail,
            get_extension_body,
            get_extension_definition,
            set_extension_state,
            get_extension_runtime,
            get_extension_runs,
            invoke_extension,
            answer_extension_input,
            write_extension_credential,
            get_extension_oauth,
            start_extension_oauth,
            complete_extension_oauth,
            forget_extension_oauth,
            disconnect_extension,
            list_agents,
            get_agent,
            invoke_agent,
            list_agent_runs,
            cancel_agent,
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
    fn stop_waits_for_session_evidence_before_killing_backend() {
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
        .expect_err("a pending session close must keep the backend alive");

        assert_eq!(events.into_inner(), vec!["close"]);
    }

    #[test]
    fn completed_close_allows_shutdown_after_drain_failure() {
        let events = RefCell::new(Vec::new());
        run_shutdown_sequence(
            || { events.borrow_mut().push("close"); Ok(()) },
            || { events.borrow_mut().push("drain"); Err("timeout".into()) },
            || { events.borrow_mut().push("kill"); Ok(()) },
        ).unwrap();
        assert_eq!(events.into_inner(), vec!["close", "drain", "kill"]);
    }

    #[test]
    fn citation_opener_accepts_only_public_web_destinations() {
        for url in ["file:///tmp/a", "javascript:alert(1)", "https://u:p@example.com", "http://127.1", "http://10.0.0.1",
                    "http://[::1]", "http://[::ffff:127.0.0.1]", "http://host.local", "https://example.com:8443",
                    "http://169.254.169.254", "http://100.64.0.1", "http://[2001:db8::1]"] {
            assert!(super::public_source_url(url).is_err(), "{url}");
        }
        assert!(super::public_source_url("https://example.com/search?q=test").is_ok());
        assert!(super::public_source_url("https://1.1.1.1/").is_ok());
    }
}
