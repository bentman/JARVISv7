use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::fs::{self, File};
use std::io::Read;
use std::path::PathBuf;
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
    stdout_log: PathBuf,
    stderr_log: PathBuf,
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

    pub fn spawn_backend(&mut self) -> Result<BackendDiagnostics, String> {
        self.kill_backend();
        let diagnostics = self.diagnostics();
        let python_path = self.python_path();
        let backend_script_path = self.backend_script_path();

        if !python_path.exists() {
            return Err(format!("backend python not found: {}\n{}", python_path.display(), format_diagnostics(&diagnostics)));
        }
        if !backend_script_path.exists() {
            return Err(format!("backend script not found: {}\n{}", backend_script_path.display(), format_diagnostics(&diagnostics)));
        }

        if let Some(parent) = self.stdout_log.parent() {
            fs::create_dir_all(parent).map_err(|err| format!("failed to create reports dir: {err}"))?;
        }
        let stdout = File::create(&self.stdout_log).map_err(|err| format!("failed to create stdout log: {err}"))?;
        let stderr = File::create(&self.stderr_log).map_err(|err| format!("failed to create stderr log: {err}"))?;

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

        let mut child = command.spawn().map_err(|err| format!("failed to spawn backend: {err}\n{}", format_diagnostics(&diagnostics)))?;
        std::thread::sleep(Duration::from_millis(350));
        if let Some(status) = child.try_wait().map_err(|err| format!("failed to inspect backend process: {err}"))? {
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
            let _ = child.kill();
            let _ = child.wait();
        }
    }

    pub fn exited_status(&mut self) -> Result<Option<String>, String> {
        if let Some(child) = self.child.as_mut() {
            if let Some(status) = child.try_wait().map_err(|err| format!("failed to inspect backend process: {err}"))? {
                self.child = None;
                return Ok(Some(status.to_string()));
            }
        }
        Ok(None)
    }

    fn python_path(&self) -> PathBuf {
        self.repo_root.join("backend").join(".venv").join("Scripts").join("python.exe")
    }

    fn backend_script_path(&self) -> PathBuf {
        self.repo_root.join("scripts").join("run_backend.py")
    }
}

impl Drop for BackendProcessManager {
    fn drop(&mut self) {
        self.kill_backend();
    }
}

pub fn wait_healthy<F>(base_url: &str, timeout: Duration, mut child_exit_status: F) -> Result<(), String>
where
    F: FnMut() -> Result<Option<String>, String>,
{
    let client = Client::builder().timeout(Duration::from_millis(700)).build().map_err(|err| format!("failed to build HTTP client: {err}"))?;
    let health_url = format!("{base_url}/health");
    let deadline = Instant::now() + timeout;
    let mut last_error = "health probe not attempted".to_string();

    while Instant::now() < deadline {
        if let Some(status) = child_exit_status()? {
            return Err(format!("backend exited before health check passed: {status}"));
        }
        match client.get(&health_url).send() {
            Ok(response) if response.status().is_success() => return Ok(()),
            Ok(response) => last_error = format!("/health returned {}", response.status()),
            Err(err) => last_error = err.to_string(),
        }
        std::thread::sleep(Duration::from_millis(250));
    }

    Err(format!("timed out waiting for /health at {health_url}: {last_error}"))
}

pub fn get_json(base_url: &str, path: &str) -> Result<String, String> {
    let response = Client::new().get(format!("{base_url}{path}")).send().map_err(|err| format!("GET {path} failed: {err}"))?;
    let status = response.status();
    let body = response.text().map_err(|err| format!("GET {path} body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("GET {path} returned {status}: {body}"));
    }
    Ok(body)
}

pub fn create_session(base_url: &str) -> Result<SessionCreateResponse, String> {
    let response = Client::new().post(format!("{base_url}/session/create")).json(&json!({})).send().map_err(|err| format!("POST /session/create failed: {err}"))?;
    let status = response.status();
    let body = response.text().map_err(|err| format!("POST /session/create body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("POST /session/create returned {status}: {body}"));
    }
    serde_json::from_str(&body).map_err(|err| format!("invalid /session/create response: {err}; body={body}"))
}

pub fn get_session_status(base_url: &str) -> Result<String, String> {
    get_json(base_url, "/session/status")
}

pub fn invoke_resident_ptt(base_url: &str) -> Result<String, String> {
    let response = Client::new().post(format!("{base_url}/session/ptt")).json(&json!({})).send().map_err(|err| format!("POST /session/ptt failed: {err}"))?;
    let status = response.status();
    let body = response.text().map_err(|err| format!("POST /session/ptt body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("POST /session/ptt returned {status}: {body}"));
    }
    Ok(body)
}

pub fn get_wake_status(base_url: &str) -> Result<String, String> {
    get_json(base_url, "/status/wake")
}

pub fn get_resident_voice_status(base_url: &str) -> Result<String, String> {
    get_json(base_url, "/status/resident-voice")
}

fn post_wake_action(base_url: &str, path: &str) -> Result<String, String> {
    let response = Client::new().post(format!("{base_url}{path}")).json(&json!({})).send().map_err(|err| format!("POST {path} failed: {err}"))?;
    let status = response.status();
    let body = response.text().map_err(|err| format!("POST {path} body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("POST {path} returned {status}: {body}"));
    }
    Ok(body)
}

pub fn start_wake_monitor(base_url: &str) -> Result<String, String> {
    post_wake_action(base_url, "/status/wake/start")
}

pub fn stop_wake_monitor(base_url: &str) -> Result<String, String> {
    post_wake_action(base_url, "/status/wake/stop")
}

pub fn toggle_wake_monitor(base_url: &str) -> Result<String, String> {
    post_wake_action(base_url, "/status/wake/toggle")
}

pub fn get_personality_list(base_url: &str) -> Result<String, String> {
    get_json(base_url, "/personality/list")
}

pub fn select_personality(base_url: &str, profile_id: &str) -> Result<String, String> {
    let response = Client::new().post(format!("{base_url}/personality/select")).json(&json!({"profile_id": profile_id})).send().map_err(|err| format!("POST /personality/select failed: {err}"))?;
    let status = response.status();
    let body = response.text().map_err(|err| format!("POST /personality/select body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("POST /personality/select returned {status}: {body}"));
    }
    Ok(body)
}

pub fn get_operator_config(base_url: &str) -> Result<String, String> {
    let response = Client::new().get(format!("{base_url}/config/operator")).send().map_err(|err| format!("GET /config/operator failed: {err}"))?;
    let status = response.status();
    let body = response.text().map_err(|err| format!("GET /config/operator body read failed: {err}"))?;
    if status.is_success() || status.as_u16() == 409 {
        return Ok(body);
    }
    Err(format!("GET /config/operator returned {status}: {body}"))
}

pub fn write_operator_config(base_url: &str, fields: Value) -> Result<String, String> {
    let response = Client::new().post(format!("{base_url}/config/operator")).json(&json!({"fields": fields})).send().map_err(|err| format!("POST /config/operator failed: {err}"))?;
    let status = response.status();
    let body = response.text().map_err(|err| format!("POST /config/operator body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("POST /config/operator returned {status}: {body}"));
    }
    Ok(body)
}

pub fn close_session(base_url: &str, session_id: &str) -> Result<(), String> {
    let response = Client::new().post(format!("{base_url}/session/close")).json(&json!({"session_id": session_id, "final_state": "IDLE"})).send().map_err(|err| format!("POST /session/close failed: {err}"))?;
    if response.status().is_success() { Ok(()) } else { Err(format!("POST /session/close returned {}", response.status())) }
}

pub fn submit_text_turn(base_url: &str, text: &str, session_id: Option<&str>) -> Result<String, String> {
    let response = Client::new().post(format!("{base_url}/task/text")).json(&json!({"text": text, "session_id": session_id})).send().map_err(|err| format!("POST /task/text failed: {err}"))?;
    let status = response.status();
    let body = response.text().map_err(|err| format!("POST /task/text body read failed: {err}"))?;
    if !status.is_success() {
        return Err(format!("POST /task/text returned {status}: {body}"));
    }
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
    if File::open(path).and_then(|mut file| file.read_to_string(&mut content)).is_err() {
        return "<unavailable>".to_string();
    }
    let mut lines = content.lines().rev().take(20).collect::<Vec<_>>();
    lines.reverse();
    lines.join("\n")
}
