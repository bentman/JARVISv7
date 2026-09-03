use reqwest::blocking::Client;
use reqwest::blocking::Response;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::fs::{self, File};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

#[derive(Debug, Serialize)]
pub struct BackendDiagnostics {
    pub python_path: String,
    pub backend_script_path: String,
    pub working_directory: String,
    pub host: String,
    pub port: u16,
    pub stdout_log: String,
    pub stderr_log: String,
}
#[derive(Debug, Deserialize, Serialize)]
pub struct SessionCreateResponse {
    pub session_id: String,
    pub state: String,
    pub turn_count: usize,
}

pub struct BackendProcessManager {
    child: Option<Child>,
    repo_root: PathBuf,
    host: String,
    port: u16,
    local_token: Option<String>,
    stdout_log: PathBuf,
    stderr_log: PathBuf,
}

#[derive(Debug, Deserialize)]
struct DaemonMetadata {
    base_url: String,
    host: String,
    port: u16,
    repo_root: String,
    token: Option<String>,
}

impl BackendProcessManager {
    pub fn new() -> Result<Self, String> {
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let repo_root = manifest_dir
            .parent()
            .and_then(|path| path.parent())
            .ok_or_else(|| "failed to resolve repo root from CARGO_MANIFEST_DIR".to_string())?
            .to_path_buf();
        let reports_dir = repo_root.join("reports");
        Ok(Self {
            child: None,
            repo_root,
            host: "127.0.0.1".to_string(),
            port: 8765,
            local_token: None,
            stdout_log: reports_dir.join("backend_startup.log"),
            stderr_log: reports_dir.join("backend_spawn_stderr.log"),
        })
    }

    pub fn diagnostics(&self) -> BackendDiagnostics {
        BackendDiagnostics {
            python_path: self.python_path().display().to_string(),
            backend_script_path: self.backend_script_path().display().to_string(),
            working_directory: self.repo_root.display().to_string(),
            host: self.host.clone(),
            port: self.port,
            stdout_log: self.stdout_log.display().to_string(),
            stderr_log: self.stderr_log.display().to_string(),
        }
    }

    pub fn base_url(&self) -> String {
        format!("http://{}:{}", self.host, self.port)
    }

    pub fn startup_failure_payload(&self, failure: &str) -> String {
        serde_json::to_string(&json!({
            "failure": failure,
            "diagnostics": self.diagnostics(),
            "stdout_tail": tail_file(&self.stdout_log),
            "stderr_tail": tail_file(&self.stderr_log),
        }))
        .unwrap_or_else(|_| failure.to_string())
    }

    pub fn spawn_backend(&mut self) -> Result<BackendDiagnostics, String> {
        if let Some(diagnostics) = self.connect_existing_daemon()? {
            return Ok(diagnostics);
        }
        let diagnostics = self.diagnostics();
        let python_path = self.python_path();
        let backend_script_path = self.backend_script_path();

        if !python_path.exists() {
            return Err(format!(
                "backend python not found: {}\n{}",
                python_path.display(),
                format_diagnostics(&diagnostics)
            ));
        }
        if !backend_script_path.exists() {
            return Err(format!(
                "backend script not found: {}\n{}",
                backend_script_path.display(),
                format_diagnostics(&diagnostics)
            ));
        }

        if let Some(parent) = self.stdout_log.parent() {
            fs::create_dir_all(parent)
                .map_err(|err| format!("failed to create reports dir: {err}"))?;
        }
        let stdout = File::create(&self.stdout_log)
            .map_err(|err| format!("failed to create stdout log: {err}"))?;
        let stderr = File::create(&self.stderr_log)
            .map_err(|err| format!("failed to create stderr log: {err}"))?;

        let mut command = Command::new(&python_path);
        command
            .arg(&backend_script_path)
            .arg("--host")
            .arg(&self.host)
            .arg("--port")
            .arg(self.port.to_string())
            .current_dir(&self.repo_root)
            .stdout(Stdio::from(stdout))
            .stderr(Stdio::from(stderr));

        #[cfg(windows)]
        command.creation_flags(CREATE_NO_WINDOW);

        let mut child = command.spawn().map_err(|err| {
            format!(
                "failed to spawn backend: {err}\n{}",
                format_diagnostics(&diagnostics)
            )
        })?;
        std::thread::sleep(Duration::from_millis(350));
        if let Some(status) = child
            .try_wait()
            .map_err(|err| format!("failed to inspect backend process: {err}"))?
        {
            return Err(format!(
                "backend exited during startup with status {status}\n{}\nstdout tail:\n{}\nstderr tail:\n{}",
                format_diagnostics(&diagnostics),
                tail_file(&self.stdout_log),
                tail_file(&self.stderr_log)
            ));
        }

        self.child = Some(child);
        Ok(diagnostics)
    }

    pub fn kill_backend(&mut self) {
        if let Some(mut child) = self.child.take() {
            let pid = child.id();
            let _ = child.kill();
            let _ = child.wait();
            self.remove_daemon_metadata_for_pid(pid);
        }
    }

    pub fn shutdown_or_kill(&mut self, client: &Client) -> Result<(), String> {
        if self.child.is_some() {
            self.kill_backend();
            return Ok(());
        }
        let Some(token) = self.local_token.clone() else {
            return Ok(());
        };
        let response = client
            .post(format!("{}/daemon/shutdown", self.base_url()))
            .header("X-JARVIS-DAEMON-TOKEN", token)
            .timeout(Duration::from_secs(5))
            .send()
            .map_err(|err| format!("POST /daemon/shutdown failed: {err}"))?;
        if !response.status().is_success() {
            return Err(format!("POST /daemon/shutdown returned {}", response.status()));
        }
        Ok(())
    }

    pub fn exited_status(&mut self) -> Result<Option<String>, String> {
        if let Some(child) = self.child.as_mut() {
            if let Some(status) = child
                .try_wait()
                .map_err(|err| format!("failed to inspect backend process: {err}"))?
            {
                self.child = None;
                return Ok(Some(status.to_string()));
            }
        }
        Ok(None)
    }

    fn python_path(&self) -> PathBuf {
        python_path_for_host(&self.repo_root, cfg!(windows))
    }

    fn backend_script_path(&self) -> PathBuf {
        self.repo_root.join("scripts").join("run_backend.py")
    }

    fn daemon_metadata_path(&self) -> PathBuf {
        self.repo_root
            .join("cache")
            .join("daemon")
            .join("backend.json")
    }

    fn daemon_lock_path(&self) -> PathBuf {
        self.repo_root
            .join("cache")
            .join("daemon")
            .join("backend.lock")
    }

    fn connect_existing_daemon(&mut self) -> Result<Option<BackendDiagnostics>, String> {
        let Some(metadata) = self.read_daemon_metadata()? else {
            return Ok(None);
        };
        if !same_path(Path::new(&metadata.repo_root), &self.repo_root) {
            return Ok(None);
        }
        if !self.daemon_status_matches(&metadata)? {
            return Ok(None);
        }
        self.host = metadata.host;
        self.port = metadata.port;
        self.local_token = metadata.token;
        self.child = None;
        Ok(Some(self.diagnostics()))
    }

    fn read_daemon_metadata(&self) -> Result<Option<DaemonMetadata>, String> {
        let path = self.daemon_metadata_path();
        let content = match fs::read_to_string(&path) {
            Ok(content) => content,
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(None),
            Err(err) => return Err(format!("failed to read daemon metadata {}: {err}", path.display())),
        };
        serde_json::from_str(&content)
            .map(Some)
            .map_err(|err| format!("invalid daemon metadata {}: {err}", path.display()))
    }

    fn daemon_status_matches(&self, metadata: &DaemonMetadata) -> Result<bool, String> {
        let response = match Client::builder()
            .timeout(Duration::from_millis(700))
            .build()
            .map_err(|err| format!("failed to build daemon probe client: {err}"))?
            .get(format!("{}/daemon/status", metadata.base_url))
            .send()
        {
            Ok(response) => response,
            Err(_) => return Ok(false),
        };
        if !response.status().is_success() {
            return Ok(false);
        }
        let status: Value = response
            .json()
            .map_err(|err| format!("invalid /daemon/status response: {err}"))?;
        Ok(status
            .get("repo_root")
            .and_then(Value::as_str)
            .is_some_and(|repo| same_path(Path::new(repo), &self.repo_root)))
    }

    fn remove_daemon_metadata_for_pid(&self, pid: u32) {
        let Ok(content) = fs::read_to_string(self.daemon_metadata_path()) else {
            return;
        };
        let Ok(metadata) = serde_json::from_str::<Value>(&content) else {
            return;
        };
        let same_repo = metadata
            .get("repo_root")
            .and_then(Value::as_str)
            .is_some_and(|repo| same_path(Path::new(repo), &self.repo_root));
        let same_pid = metadata
            .get("pid")
            .and_then(Value::as_u64)
            .is_some_and(|metadata_pid| metadata_pid == u64::from(pid));
        if same_repo && same_pid {
            let _ = fs::remove_file(self.daemon_metadata_path());
            let _ = fs::remove_file(self.daemon_lock_path());
        }
    }
}

fn python_path_for_host(repo_root: &Path, is_windows: bool) -> PathBuf {
    let venv_root = repo_root.join("backend").join(".venv");
    if is_windows {
        venv_root.join("Scripts").join("python.exe")
    } else {
        venv_root.join("bin").join("python")
    }
}

fn same_path(left: &Path, right: &Path) -> bool {
    let left = fs::canonicalize(left).unwrap_or_else(|_| left.to_path_buf());
    let right = fs::canonicalize(right).unwrap_or_else(|_| right.to_path_buf());
    left == right
}

impl Drop for BackendProcessManager {
    fn drop(&mut self) {
        self.kill_backend();
    }
}

pub fn wait_healthy<F>(
    client: &Client,
    base_url: &str,
    timeout: Duration,
    mut child_exit_status: F,
) -> Result<(), String>
where
    F: FnMut() -> Result<Option<String>, String>,
{
    let health_url = format!("{base_url}/health");
    let deadline = Instant::now() + timeout;
    let mut last_error = "health probe not attempted".to_string();

    while Instant::now() < deadline {
        if let Some(status) = child_exit_status()? {
            return Err(format!(
                "backend exited before health check passed: {status}"
            ));
        }
        match client
            .get(&health_url)
            .timeout(Duration::from_millis(700))
            .send()
        {
            Ok(response) if response.status().is_success() => return Ok(()),
            Ok(response) => last_error = format!("/health returned {}", response.status()),
            Err(err) => last_error = err.to_string(),
        }
        std::thread::sleep(Duration::from_millis(250));
    }

    Err(format!(
        "timed out waiting for /health at {health_url}: {last_error}"
    ))
}

pub fn get_json(client: &Client, base_url: &str, path: &str) -> Result<String, String> {
    let response = client
        .get(format!("{base_url}{path}"))
        .send()
        .map_err(|err| format!("GET {path} failed: {err}"))?;
    let status = response.status();
    let body = response
        .text()
        .map_err(|err| format!("GET {path} body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("GET {path} returned {status}: {body}"));
    }
    Ok(body)
}

pub fn create_session(client: &Client, base_url: &str) -> Result<SessionCreateResponse, String> {
    let response = client
        .post(format!("{base_url}/session/create"))
        .json(&json!({}))
        .send()
        .map_err(|err| format!("POST /session/create failed: {err}"))?;
    let status = response.status();
    let body = response
        .text()
        .map_err(|err| format!("POST /session/create body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("POST /session/create returned {status}: {body}"));
    }
    serde_json::from_str(&body)
        .map_err(|err| format!("invalid /session/create response: {err}; body={body}"))
}

pub fn get_session_status(client: &Client, base_url: &str) -> Result<String, String> {
    get_json(client, base_url, "/session/status")
}

pub fn get_desktop_status(client: &Client, base_url: &str) -> Result<String, String> {
    get_json(client, base_url, "/status/desktop")
}

pub fn invoke_resident_ptt(client: &Client, base_url: &str) -> Result<String, String> {
    let response = client
        .post(format!("{base_url}/session/ptt"))
        .json(&json!({}))
        .send()
        .map_err(|err| format!("POST /session/ptt failed: {err}"))?;
    let status = response.status();
    let body = response
        .text()
        .map_err(|err| format!("POST /session/ptt body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("POST /session/ptt returned {status}: {body}"));
    }
    Ok(body)
}

pub fn get_wake_status(client: &Client, base_url: &str) -> Result<String, String> {
    get_json(client, base_url, "/status/wake")
}

pub fn get_resident_voice_status(client: &Client, base_url: &str) -> Result<String, String> {
    get_json(client, base_url, "/status/resident-voice")
}

pub fn start_resident_voice_stream(client: &Client, base_url: &str) -> Result<String, String> {
    post_resident_voice_action(client, base_url, "/status/resident-voice/start")
}

pub fn stop_resident_voice_stream(client: &Client, base_url: &str) -> Result<String, String> {
    post_resident_voice_action(client, base_url, "/status/resident-voice/stop")
}

pub fn set_resident_voice_mode(
    client: &Client,
    base_url: &str,
    mode: &str,
) -> Result<String, String> {
    let response = client
        .put(format!("{base_url}/status/resident-voice/mode"))
        .json(&json!({"mode": mode}))
        .send()
        .map_err(|err| format!("PUT /status/resident-voice/mode failed: {err}"))?;
    let status = response.status();
    let body = response
        .text()
        .map_err(|err| format!("PUT /status/resident-voice/mode body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!(
            "PUT /status/resident-voice/mode returned {status}: {body}"
        ));
    }
    Ok(body)
}

pub fn set_resident_voice_tts_voice(
    client: &Client,
    base_url: &str,
    voice: &str,
) -> Result<String, String> {
    let response = client
        .put(format!("{base_url}/status/resident-voice/tts-voice"))
        .json(&json!({"voice": voice}))
        .send()
        .map_err(|err| format!("PUT /status/resident-voice/tts-voice failed: {err}"))?;
    let status = response.status();
    let body = response
        .text()
        .map_err(|err| format!("PUT /status/resident-voice/tts-voice body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!(
            "PUT /status/resident-voice/tts-voice returned {status}: {body}"
        ));
    }
    Ok(body)
}

fn post_resident_voice_action(
    client: &Client,
    base_url: &str,
    path: &str,
) -> Result<String, String> {
    let response = client
        .post(format!("{base_url}{path}"))
        .json(&json!({}))
        .send()
        .map_err(|err| format!("POST {path} failed: {err}"))?;
    let status = response.status();
    let body = response
        .text()
        .map_err(|err| format!("POST {path} body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("POST {path} returned {status}: {body}"));
    }
    Ok(body)
}

fn post_wake_action(client: &Client, base_url: &str, path: &str) -> Result<String, String> {
    let response = client
        .post(format!("{base_url}{path}"))
        .json(&json!({}))
        .send()
        .map_err(|err| format!("POST {path} failed: {err}"))?;
    let status = response.status();
    let body = response
        .text()
        .map_err(|err| format!("POST {path} body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("POST {path} returned {status}: {body}"));
    }
    Ok(body)
}

pub fn start_wake_monitor(client: &Client, base_url: &str) -> Result<String, String> {
    post_wake_action(client, base_url, "/status/wake/start")
}

pub fn stop_wake_monitor(client: &Client, base_url: &str) -> Result<String, String> {
    post_wake_action(client, base_url, "/status/wake/stop")
}

pub fn toggle_wake_monitor(client: &Client, base_url: &str) -> Result<String, String> {
    post_wake_action(client, base_url, "/status/wake/toggle")
}

pub fn get_personality_list(client: &Client, base_url: &str) -> Result<String, String> {
    get_json(client, base_url, "/personality/list")
}

pub fn select_personality(
    client: &Client,
    base_url: &str,
    profile_id: &str,
) -> Result<String, String> {
    let response = client
        .post(format!("{base_url}/personality/select"))
        .json(&json!({"profile_id": profile_id}))
        .send()
        .map_err(|err| format!("POST /personality/select failed: {err}"))?;
    let status = response.status();
    let body = response
        .text()
        .map_err(|err| format!("POST /personality/select body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!(
            "POST /personality/select returned {status}: {body}"
        ));
    }
    Ok(body)
}

pub fn get_operator_config(client: &Client, base_url: &str) -> Result<String, String> {
    let response = client
        .get(format!("{base_url}/config/operator"))
        .send()
        .map_err(|err| format!("GET /config/operator failed: {err}"))?;
    let status = response.status();
    let body = response
        .text()
        .map_err(|err| format!("GET /config/operator body read failed: {err}"))?;
    if status.is_success() || status.as_u16() == 409 {
        return Ok(body);
    }
    Err(format!("GET /config/operator returned {status}: {body}"))
}

pub fn write_operator_config(
    client: &Client,
    base_url: &str,
    fields: Value,
) -> Result<String, String> {
    let response = client
        .post(format!("{base_url}/config/operator"))
        .json(&json!({"fields": fields}))
        .send()
        .map_err(|err| format!("POST /config/operator failed: {err}"))?;
    let status = response.status();
    let body = response
        .text()
        .map_err(|err| format!("POST /config/operator body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("POST /config/operator returned {status}: {body}"));
    }
    Ok(body)
}

pub fn get_llm_config(client: &Client, base_url: &str) -> Result<String, String> {
    let operation = "GET /config/llm";
    let response = client
        .get(format!("{base_url}/config/llm"))
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

pub fn create_llm_profile(
    client: &Client,
    base_url: &str,
    profile: Value,
) -> Result<String, String> {
    let operation = "POST /config/llm/profiles";
    let response = client
        .post(format!("{base_url}/config/llm/profiles"))
        .json(&profile)
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

pub fn update_llm_profile(
    client: &Client,
    base_url: &str,
    profile_id: &str,
    profile: Value,
) -> Result<String, String> {
    let operation = "PUT /config/llm/profiles";
    let response = client
        .put(format!("{base_url}/config/llm/profiles/{profile_id}"))
        .json(&profile)
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

pub fn delete_llm_profile(
    client: &Client,
    base_url: &str,
    profile_id: &str,
) -> Result<String, String> {
    let operation = "DELETE /config/llm/profiles";
    let response = client
        .delete(format!("{base_url}/config/llm/profiles/{profile_id}"))
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

pub fn test_llm_profile(
    client: &Client,
    base_url: &str,
    profile_id: &str,
) -> Result<String, String> {
    let operation = "POST /config/llm/profiles/test";
    let response = client
        .post(format!("{base_url}/config/llm/profiles/{profile_id}/test"))
        .json(&json!({}))
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

pub fn update_llm_selection(
    client: &Client,
    base_url: &str,
    selection: Value,
) -> Result<String, String> {
    let operation = "PUT /config/llm/selection";
    let response = client
        .put(format!("{base_url}/config/llm/selection"))
        .json(&selection)
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

pub fn rotate_secret_store_key(client: &Client, base_url: &str) -> Result<String, String> {
    let operation = "POST /config/secrets/rotate";
    let response = client
        .post(format!("{base_url}/config/secrets/rotate"))
        .json(&json!({}))
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

fn memory_transport_error(operation: &str, error: reqwest::Error) -> String {
    json!({
        "status": Value::Null,
        "body": Value::Null,
        "message": format!("{operation} failed: {error}"),
    })
    .to_string()
}

fn memory_response(operation: &str, response: Response) -> Result<String, String> {
    let status = response.status();
    let body = response
        .text()
        .map_err(|error| memory_transport_error(operation, error))?;
    if status.is_success() {
        return Ok(body);
    }
    let structured_body =
        serde_json::from_str::<Value>(&body).unwrap_or_else(|_| json!({ "message": body }));
    Err(json!({
        "status": status.as_u16(),
        "body": structured_body,
    })
    .to_string())
}

pub fn get_memory_policy(client: &Client, base_url: &str) -> Result<String, String> {
    let operation = "GET /memory/policy";
    let response = client
        .get(format!("{base_url}/memory/policy"))
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

pub fn update_memory_policy(
    client: &Client,
    base_url: &str,
    automatic_curation_enabled: bool,
    expected_revision: u64,
) -> Result<String, String> {
    let operation = "PUT /memory/policy";
    let response = client
        .put(format!("{base_url}/memory/policy"))
        .json(&json!({
            "automatic_curation_enabled": automatic_curation_enabled,
            "expected_revision": expected_revision,
        }))
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

pub fn list_memories(
    client: &Client,
    base_url: &str,
    state: Option<&str>,
    kind: Option<&str>,
    query: Option<&str>,
    offset: u32,
    limit: u32,
) -> Result<String, String> {
    let operation = "GET /memory";
    let mut params = vec![("offset", offset.to_string()), ("limit", limit.to_string())];
    if let Some(value) = state {
        params.push(("state", value.to_string()));
    }
    if let Some(value) = kind {
        params.push(("kind", value.to_string()));
    }
    if let Some(value) = query {
        params.push(("query", value.to_string()));
    }
    let response = client
        .get(format!("{base_url}/memory"))
        .query(&params)
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

pub fn get_memory_detail(client: &Client, base_url: &str, fact_id: &str) -> Result<String, String> {
    let operation = "GET /memory/{fact_id}";
    let response = client
        .get(format!("{base_url}/memory/{fact_id}"))
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

fn post_memory_action(
    client: &Client,
    base_url: &str,
    fact_id: &str,
    action: &str,
    body: Value,
) -> Result<String, String> {
    let operation = format!("POST /memory/{{fact_id}}/{action}");
    let response = client
        .post(format!("{base_url}/memory/{fact_id}/{action}"))
        .json(&body)
        .send()
        .map_err(|error| memory_transport_error(&operation, error))?;
    memory_response(&operation, response)
}

pub fn confirm_memory(
    client: &Client,
    base_url: &str,
    fact_id: &str,
    expected_revision: u64,
    reason: Option<&str>,
) -> Result<String, String> {
    post_memory_action(
        client,
        base_url,
        fact_id,
        "confirm",
        json!({ "expected_revision": expected_revision, "reason": reason }),
    )
}

pub fn correct_memory(
    client: &Client,
    base_url: &str,
    fact_id: &str,
    expected_revision: u64,
    replacement_text: &str,
    replacement_value: Option<&str>,
    reason: Option<&str>,
) -> Result<String, String> {
    post_memory_action(
        client,
        base_url,
        fact_id,
        "correct",
        json!({
            "expected_revision": expected_revision,
            "replacement_text": replacement_text,
            "replacement_value": replacement_value,
            "reason": reason,
        }),
    )
}

pub fn dispute_memory(
    client: &Client,
    base_url: &str,
    fact_id: &str,
    expected_revision: u64,
    reason: Option<&str>,
) -> Result<String, String> {
    post_memory_action(
        client,
        base_url,
        fact_id,
        "dispute",
        json!({ "expected_revision": expected_revision, "reason": reason }),
    )
}

pub fn forget_memory(
    client: &Client,
    base_url: &str,
    fact_id: &str,
    expected_revision: u64,
    reason: Option<&str>,
) -> Result<String, String> {
    let operation = "DELETE /memory/{fact_id}";
    let mut params = vec![("expected_revision", expected_revision.to_string())];
    if let Some(value) = reason {
        params.push(("reason", value.to_string()));
    }
    let response = client
        .delete(format!("{base_url}/memory/{fact_id}"))
        .query(&params)
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

pub fn get_memory_curation_status(client: &Client, base_url: &str) -> Result<String, String> {
    let operation = "GET /memory/curation/status";
    let response = client
        .get(format!("{base_url}/memory/curation/status"))
        .send()
        .map_err(|error| memory_transport_error(operation, error))?;
    memory_response(operation, response)
}

pub fn close_session(client: &Client, base_url: &str, session_id: &str) -> Result<(), String> {
    let response = client
        .post(format!("{base_url}/session/close"))
        .timeout(Duration::from_secs(12))
        .json(&json!({"session_id": session_id, "final_state": "IDLE"}))
        .send()
        .map_err(|err| format!("POST /session/close failed: {err}"))?;
    if response.status().is_success() || response.status().as_u16() == 404 {
        Ok(())
    } else {
        Err(format!(
            "POST /session/close returned {}",
            response.status()
        ))
    }
}

pub fn drain_memory_curation(client: &Client, base_url: &str) -> Result<(), String> {
    let response = client
        .post(format!("{base_url}/memory/curation/drain"))
        .timeout(Duration::from_secs(10))
        .json(&json!({}))
        .send()
        .map_err(|err| format!("POST /memory/curation/drain failed: {err}"))?;
    if response.status().is_success() {
        Ok(())
    } else {
        Err(format!(
            "POST /memory/curation/drain returned {}",
            response.status()
        ))
    }
}

pub fn submit_text_turn(
    client: &Client,
    base_url: &str,
    text: &str,
    session_id: Option<&str>,
) -> Result<String, String> {
    let response = client
        .post(format!("{base_url}/task/text"))
        .json(&json!({"text": text, "session_id": session_id}))
        .send()
        .map_err(|err| format!("POST /task/text failed: {err}"))?;
    let status = response.status();
    let body = response
        .text()
        .map_err(|err| format!("POST /task/text body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("POST /task/text returned {status}: {body}"));
    }
    Ok(body)
}

pub fn cancel_search(client: &Client, base_url: &str, session_id: &str, turn_id: &str) -> Result<String, String> {
    let response = client.post(format!("{base_url}/session/search/cancel"))
        .timeout(Duration::from_secs(5))
        .json(&json!({"session_id": session_id, "turn_id": turn_id}))
        .send().map_err(|error| format!("search cancellation failed: {error}"))?;
    let status = response.status();
    let body = response.text().map_err(|error| error.to_string())?;
    if !status.is_success() { return Err(format!("search cancellation returned {status}")); }
    Ok(body)
}

fn format_diagnostics(diagnostics: &BackendDiagnostics) -> String {
    format!(
        "python={}\nscript={}\nworking_directory={}\nhost={}\nport={}\nstdout_log={}\nstderr_log={}",
        diagnostics.python_path,
        diagnostics.backend_script_path,
        diagnostics.working_directory,
        diagnostics.host,
        diagnostics.port,
        diagnostics.stdout_log,
        diagnostics.stderr_log
    )
}

fn tail_file(path: &PathBuf) -> String {
    let mut content = String::new();
    if File::open(path)
        .and_then(|mut file| file.read_to_string(&mut content))
        .is_err()
    {
        return "<unavailable>".to_string();
    }
    let mut lines = content.lines().rev().take(20).collect::<Vec<_>>();
    lines.reverse();
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::python_path_for_host;
    #[cfg(target_os = "linux")]
    use super::{BackendProcessManager, Client, Duration};
    use std::path::Path;

    #[test]
    fn resolves_windows_backend_interpreter_path() {
        assert_eq!(
            python_path_for_host(Path::new("/repo"), true),
            Path::new("/repo/backend/.venv/Scripts/python.exe")
        );
    }

    #[test]
    fn resolves_linux_backend_interpreter_path() {
        assert_eq!(
            python_path_for_host(Path::new("/repo"), false),
            Path::new("/repo/backend/.venv/bin/python")
        );
    }

    #[test]
    fn shutdown_requests_use_explicit_timeouts_and_post_drain() {
        let source = include_str!("backend.rs");
        assert!(source.contains(".timeout(Duration::from_secs(5))"));
        assert!(source.contains(".timeout(Duration::from_secs(10))"));
        assert!(source.contains(".post(format!(\"{base_url}/memory/curation/drain\"))"));
        assert!(!source.contains(".get(format!(\"{base_url}/memory/curation/drain\"))"));
    }

    #[test]
    fn backend_manager_does_not_kill_unrelated_port_owner() {
        let source = include_str!("backend.rs");
        let windows_kill_command =
            String::from_utf8(vec![116, 97, 115, 107, 107, 105, 108, 108]).unwrap();
        let port_scan_command = format!("{}{}", "netstat", " -ano");
        assert!(!source.contains(&windows_kill_command));
        assert!(!source.contains(&port_scan_command));
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn linux_backend_manager_reaches_health() {
        let mut manager = BackendProcessManager::new().expect("backend manager");
        assert!(manager.python_path().is_file());
        manager.spawn_backend().expect("backend launch");

        let client = Client::builder().build().expect("health client");
        let base_url = manager.base_url();
        let result = super::wait_healthy(&client, &base_url, Duration::from_secs(90), || {
            manager.exited_status()
        });
        manager.kill_backend();
        result.expect("desktop-launched backend health");
    }
}
