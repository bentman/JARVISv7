function pushLine(lines, label, value) {
  const text = String(value ?? "").trim();
  if (!text) return;
  lines.push(`${label}: ${text}`);
}

function pushBlock(lines, label, value) {
  const text = String(value ?? "").trim();
  if (!text) return;
  lines.push(`${label}:`);
  lines.push(text);
}

export function renderBackendDiagnostics(payload, detailEl) {
  if (!detailEl) return;
  const diagnostics = payload?.diagnostics || payload || {};
  const lines = [];
  const endpoint = diagnostics.host && diagnostics.port ? `${diagnostics.host}:${diagnostics.port}` : diagnostics.endpoint;

  pushLine(lines, "failure", payload?.failure);
  pushLine(lines, "python_path", diagnostics.python_path);
  pushLine(lines, "backend_script_path", diagnostics.backend_script_path);
  pushLine(lines, "working_directory", diagnostics.working_directory);
  pushLine(lines, "endpoint", endpoint);
  pushLine(lines, "stdout_log", diagnostics.stdout_log);
  pushLine(lines, "stderr_log", diagnostics.stderr_log);
  pushBlock(lines, "stdout_tail", payload?.stdout_tail);
  pushBlock(lines, "stderr_tail", payload?.stderr_tail);

  detailEl.textContent = lines.join("\n");
}

export function clearBackendDiagnostics(detailEl) {
  if (!detailEl) return;
  detailEl.textContent = "";
}
