import { formatTime, formatValue } from "./ui/format.js";

function statusKind(value) {
  const normalized = String(value ?? "").trim().toLowerCase();
  if (["yes", "running", "enabled", "ready", "reachable"].includes(normalized)) return "positive";
  if (["no", "stopped", "disabled", "unavailable", "failed"].includes(normalized)) return "negative";
  return "neutral";
}

function appendField(containerEl, label, value) {
  const row = document.createElement("div");
  row.className = "wake-indicator-field";

  const labelEl = document.createElement("span");
  labelEl.className = "wake-indicator-label";
  labelEl.textContent = label;

  const valueEl = document.createElement("span");
  valueEl.className = "wake-indicator-value status-value";
  valueEl.dataset.status = statusKind(value);
  valueEl.textContent = value;

  row.append(labelEl, valueEl);
  containerEl.appendChild(row);
}

export function renderWakeStatus(wakePayload, containerEl) {
  if (!containerEl) return;

  containerEl.replaceChildren();

  const provider = wakePayload?.provider || "unknown";
  const available = Boolean(wakePayload?.available);
  const active = Boolean(wakePayload?.active || wakePayload?.enabled);
  const monitoring = Boolean(wakePayload?.monitoring);
  const reason = wakePayload?.reason || "";
  const detectionCount = Number(wakePayload?.detection_count || 0);
  const lastDetected = wakePayload?.last_detected ? formatTime(wakePayload.last_detected) : "Never";
  const lastScore = wakePayload?.last_score;
  const threshold = wakePayload?.threshold;
  const scoreText = `${formatDiagnostic(lastScore)} / ${formatDiagnostic(threshold)}`;

  const summary = document.createElement("p");
  summary.className = "wake-indicator-summary";
  if (available && (active || monitoring)) {
    summary.textContent = `Wake monitoring active via ${provider}.`;
  } else if (available) {
    summary.textContent = `Wake provider ${provider} is inactive; manual PTT is active.`;
  } else {
    summary.textContent = `Manual PTT only; wake provider ${provider} is unavailable.`;
  }

  const fields = document.createElement("div");
  fields.className = "wake-indicator-fields";
  appendField(fields, "Provider", provider);
  appendField(fields, "Available", formatValue(available));
  appendField(fields, "Enabled", formatValue(active));
  appendField(fields, "Listening", formatValue(monitoring));
  appendField(fields, "Detections", String(detectionCount));
  appendField(fields, "Last detected", lastDetected);
  appendField(fields, "Score / threshold", scoreText);
  if (reason) appendField(fields, "Reason", reason);

  containerEl.dataset.available = String(available);
  containerEl.dataset.active = String(active);
  containerEl.dataset.monitoring = String(monitoring);
  containerEl.append(summary, fields);
}

function formatDiagnostic(value) {
  return Number.isFinite(Number(value)) ? Number(value).toFixed(3) : "n/a";
}
