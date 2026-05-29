import { applyStored, initAppearanceControls } from "./components/appearance-controls.js";
import { renderDegradedList } from "./components/degraded-list.js";
import { renderReadiness as renderReadinessPanel } from "./components/readiness-panel.js";
import { renderServiceStatus } from "./components/service-status.js";
import { closeSettings, openSettings } from "./components/settings-panel.js";
import { setStateLabel } from "./components/state-label.js";
import { renderWakeStatus } from "./components/wake-indicator.js";

const stateEl = document.querySelector("#startup-state");
const healthEl = document.querySelector("#backend-health");
const sessionEl = document.querySelector("#session-id");
const turnCountEl = document.querySelector("#session-turn-count");
const wakeIndicatorEl = document.querySelector("#wake-indicator");
const wakeToggleEl = document.querySelector("#wake-toggle");
const personalityCurrentEl = document.querySelector("#personality-current");
const personalitySelectEl = document.querySelector("#personality-select");
const personalityDetailEl = document.querySelector("#personality-detail");
const settingsTriggerEl = document.querySelector("#settings-trigger");
const settingsRestartRequiredEl = document.querySelector("#settings-restart-required");
const settingsPanelEl = document.querySelector("#settings-panel");
const readinessEl = document.querySelector("#readiness-panel");
const degradedEl = document.querySelector("#degraded-conditions");
const serviceStatusEl = document.querySelector("#service-status");
const appearanceControlsEl = document.querySelector("#appearance-controls");
const errorEl = document.querySelector("#error-panel");
const logEl = document.querySelector("#conversation-log");
const turnStateEl = document.querySelector("#turn-state");
const formEl = document.querySelector("#text-form");
const inputEl = document.querySelector("#text-input");
const sendButton = document.querySelector("#send-button");
const pttButton = document.querySelector("#ptt-button");
const voiceStatusEl = document.querySelector("#voice-status");
const voiceDetailEl = document.querySelector("#voice-detail");

const invoke = window.__TAURI__?.core?.invoke;
let activePersonalityId = "default";
let wakePollTimer = null;
let sessionPollTimer = null;
let lastRenderedResidentTurnKey = "";

const presenceByProfile = {
  default: { listening: "Listening.", transcribing: "Transcribing.", reasoning: "Understood." },
  concise: { listening: "Listening.", transcribing: "Transcribing.", reasoning: "On it." },
  warm: { listening: "Go ahead.", transcribing: "I’m transcribing that.", reasoning: "I’m on it." },
};

function setState(value, degraded = false) {
  setStateLabel(value, stateEl);
  document.body.dataset.degraded = degraded ? "true" : "false";
}

function showError(message) {
  errorEl.textContent = message;
  errorEl.classList.remove("hidden");
  setState("FAILED");
}

function clearError() {
  errorEl.textContent = "";
  errorEl.classList.add("hidden");
}

function appendMessage(role, text) {
  const entry = document.createElement("article");
  const stampEl = document.createElement("span");
  const roleEl = document.createElement("strong");
  const bodyEl = document.createElement("p");
  entry.className = `message ${role}`;
  stampEl.className = "stamp";
  stampEl.textContent = new Date().toLocaleTimeString();
  roleEl.textContent = role;
  bodyEl.textContent = text || "(no text returned)";
  entry.append(stampEl, roleEl, bodyEl);
  logEl.appendChild(entry);
  logEl.scrollTop = logEl.scrollHeight;
}

function appendToolCalls(toolCalls) {
  if (!Array.isArray(toolCalls) || toolCalls.length === 0) return;
  for (const call of toolCalls) {
    const toolName = call.tool_name || "unknown";
    const summary = String(call.tool_output_summary || "").slice(0, 200);
    appendMessage("system", `Tool used: ${toolName} | ${summary}`);
  }
}

function presenceText(stateName) {
  const profile = presenceByProfile[activePersonalityId] || presenceByProfile.default;
  return profile[stateName] || presenceByProfile.default[stateName];
}

function appendPresence(stateName) {
  appendMessage("presence", presenceText(stateName));
}

function updatePersonalityDisplay(profile) {
  activePersonalityId = profile.profile_id || activePersonalityId;
  personalityCurrentEl.textContent = activePersonalityId;
  const metadataFields = [
    ["Tone", profile.tone],
    ["Brevity", profile.brevity],
    ["Formality", profile.formality],
  ];
  const heading = document.createElement("strong");
  heading.textContent = profile.display_name || "JARVIS";
  const rows = metadataFields.map(([label, value]) => {
    const row = document.createElement("div");
    const labelEl = document.createElement("span");
    const valueEl = document.createElement("span");
    labelEl.textContent = `${label}: `;
    valueEl.textContent = value || "—";
    row.append(labelEl, valueEl);
    return row;
  });
  personalityDetailEl.replaceChildren(heading, ...rows);
}

function setVoiceDetail(result) {
  const lines = [
    `state: ${result.state ?? ""}`,
    `source: ${result.invocation_source ?? ""}`,
    `transcript: ${result.last_transcript ?? ""}`,
    `response: ${result.last_response ?? ""}`,
    `failure_reason: ${result.failure_reason ?? ""}`,
    `tts_output_device: ${result.tts_output_device ?? ""}`,
    `turn_count: ${result.turn_count ?? 0}`,
  ];
  voiceDetailEl.textContent = lines.join("\n");
}

function setCaptureState(state) {
  pttButton.dataset.captureState = state;
  if (state === "processing") {
    pttButton.disabled = true;
    pttButton.setAttribute("aria-pressed", "false");
    pttButton.textContent = "Voice Running…";
    return;
  }
  pttButton.disabled = false;
  pttButton.setAttribute("aria-pressed", "false");
  pttButton.textContent = "Start Voice";
}

function renderReadiness(readiness) {
  renderReadinessPanel(readiness, readinessEl);
  renderDegradedList(readiness, degradedEl);
  renderServiceStatus(readiness.services, serviceStatusEl);
  setState(readiness.requires_degraded_mode || readiness.status !== "ready" ? "DEGRADED" : "READY", readiness.requires_degraded_mode);
}

async function refreshSessionStatus() {
  const status = JSON.parse(await invoke("get_session_status"));
  sessionEl.textContent = status.session_id || "not active";
  if (turnCountEl) turnCountEl.textContent = String(status.turn_count ?? 0);
  renderResidentVoiceStatus(status);
  return status;
}

function startSessionPolling() {
  if (sessionPollTimer) window.clearInterval(sessionPollTimer);
  sessionPollTimer = window.setInterval(() => {
    refreshSessionStatus().catch(() => undefined);
  }, 1000);
}

function stopSessionPolling() {
  if (!sessionPollTimer) return;
  window.clearInterval(sessionPollTimer);
  sessionPollTimer = null;
}

function renderResidentVoiceStatus(status) {
  setVoiceDetail(status);
  const state = status.state || "IDLE";
  setStateLabel(state, turnStateEl);
  const source = status.invocation_source || "";
  const isResidentVoice = source === "ptt" || source === "wake";
  if (!isResidentVoice) return;

  if (state === "LISTENING") {
    setCaptureState("processing");
    voiceStatusEl.textContent = `${source.toUpperCase()} listening`;
    setState("LISTENING");
    return;
  }
  if (["TRANSCRIBING", "REASONING", "ACTING", "RESPONDING", "SPEAKING"].includes(state)) {
    setCaptureState("processing");
    voiceStatusEl.textContent = `${source.toUpperCase()} ${state.toLowerCase()}`;
    setState(state);
    return;
  }
  if (state === "FAILED") {
    setCaptureState("idle");
    voiceStatusEl.textContent = "Voice failed";
    if (status.failure_reason) showError(status.failure_reason);
    appendResidentVoiceCompletion(status);
    return;
  }
  if (state === "IDLE") {
    setCaptureState("idle");
    voiceStatusEl.textContent = status.last_transcript || status.last_response ? "Voice complete" : "Voice idle";
    appendResidentVoiceCompletion(status);
  }
}

function appendResidentVoiceCompletion(status) {
  if (!status.last_transcript && !status.last_response && !status.failure_reason) return;
  const key = [
    status.invocation_source ?? "",
    status.last_transcript ?? "",
    status.last_response ?? "",
    status.failure_reason ?? "",
  ].join("|");
  if (key === lastRenderedResidentTurnKey) return;
  lastRenderedResidentTurnKey = key;
  if (status.last_transcript) appendMessage("user", status.last_transcript);
  appendMessage("assistant", status.last_response || status.failure_reason);
}

async function refreshWakeStatus() {
  try {
    const status = JSON.parse(await invoke("get_wake_status"));
    renderWakeStatus(status, wakeIndicatorEl);
    if (wakeToggleEl) {
      wakeToggleEl.disabled = !status.available;
      wakeToggleEl.textContent = status.active || status.monitoring ? "Stop" : "Start";
      wakeToggleEl.setAttribute("aria-pressed", status.active || status.monitoring ? "true" : "false");
    }
    return status;
  } catch (error) {
    renderWakeStatus(
      {
        provider: "unknown",
        available: false,
        monitoring: false,
        active: false,
        enabled: false,
        reason: `Wake status unavailable; PTT-only fallback is active. Reason: ${String(error)}`,
      },
      wakeIndicatorEl,
    );
    if (wakeToggleEl) {
      wakeToggleEl.disabled = true;
      wakeToggleEl.textContent = "Start";
      wakeToggleEl.setAttribute("aria-pressed", "false");
    }
    return null;
  }
}

function startWakePolling() {
  if (wakePollTimer) window.clearInterval(wakePollTimer);
  wakePollTimer = window.setInterval(() => {
    refreshWakeStatus().catch(() => undefined);
  }, 1500);
}

function stopWakePolling() {
  if (!wakePollTimer) return;
  window.clearInterval(wakePollTimer);
  wakePollTimer = null;
}

async function startWakeMonitorIfAvailable() {
  const status = await refreshWakeStatus();
  if (!status?.available || status.active || status.monitoring) return status;
  const started = JSON.parse(await invoke("start_wake_monitor"));
  renderWakeStatus(started, wakeIndicatorEl);
  if (wakeToggleEl) {
    wakeToggleEl.disabled = !started.available;
    wakeToggleEl.textContent = started.active || started.monitoring ? "Stop" : "Start";
    wakeToggleEl.setAttribute("aria-pressed", started.active || started.monitoring ? "true" : "false");
  }
  return started;
}

async function refreshPersonalityProfiles() {
  const payload = JSON.parse(await invoke("get_personality_list"));
  activePersonalityId = payload.active_profile_id || "default";
  personalitySelectEl.innerHTML = "";
  for (const profile of payload.profiles || []) {
    const option = document.createElement("option");
    option.value = profile.profile_id;
    option.textContent = `${profile.display_name} (${profile.profile_id})`;
    option.selected = profile.profile_id === activePersonalityId;
    personalitySelectEl.appendChild(option);
    if (option.selected) updatePersonalityDisplay(profile);
  }
  personalitySelectEl.disabled = false;
  return payload;
}

async function selectPersonality(profileId) {
  const before = await refreshSessionStatus();
  const payload = JSON.parse(await invoke("select_personality", { profileId }));
  updatePersonalityDisplay(payload.active);
  const after = await refreshSessionStatus();
  appendMessage("system", `Personality switched to ${payload.active.profile_id}; applies to the next turn. Session preserved: ${before.session_id === after.session_id}.`);
}

async function startDesktop() {
  clearError();
  setState("STARTING");
  healthEl.textContent = "starting";
  sendButton.disabled = true;
  inputEl.disabled = true;
  pttButton.disabled = true;

  if (!invoke) {
    showError("Tauri command bridge is unavailable; desktop backend lifecycle cannot start.");
    healthEl.textContent = "error";
    return;
  }

  try {
    const startPayload = JSON.parse(await invoke("start_backend"));
    sessionEl.textContent = startPayload.session_id || "created";
    if (turnCountEl) turnCountEl.textContent = String(startPayload.turn_count ?? 0);
    healthEl.textContent = "ok";
    const readiness = JSON.parse(await invoke("get_readiness"));
    renderReadiness(readiness);
    await refreshSessionStatus();
    await startWakeMonitorIfAvailable();
    startWakePolling();
    startSessionPolling();
    await refreshPersonalityProfiles();
    appendMessage("system", "Backend started and readiness loaded.");
    sendButton.disabled = false;
    inputEl.disabled = false;
    pttButton.disabled = false;
    inputEl.focus();
  } catch (error) {
    healthEl.textContent = "error";
    showError(String(error));
  }
}

async function restartBackendForSettings() {
  await invoke("stop_backend");
  setState("STARTING");
  healthEl.textContent = "starting";
  const startPayload = JSON.parse(await invoke("start_backend"));
  sessionEl.textContent = startPayload.session_id || "created";
  if (turnCountEl) turnCountEl.textContent = String(startPayload.turn_count ?? 0);
  healthEl.textContent = "ok";
  const readiness = JSON.parse(await invoke("get_readiness"));
  renderReadiness(readiness);
  await startWakeMonitorIfAvailable();
  startWakePolling();
  startSessionPolling();
}

function updateSettingsRestartRequired(required, details = {}) {
  if (!settingsRestartRequiredEl) return;
  settingsRestartRequiredEl.hidden = !(required && !details.panelOpen);
  settingsRestartRequiredEl.textContent = required ? "Restart required" : "";
}

async function invokeResidentPtt() {
  if (pttButton.dataset.captureState !== "idle") return;
  clearError();
  setCaptureState("processing");
  voiceStatusEl.textContent = "PTT invoked";
  setState("LISTENING");
  appendPresence("listening");
  try {
    const status = JSON.parse(await invoke("invoke_resident_ptt"));
    renderResidentVoiceStatus(status);
    await refreshSessionStatus();
  } catch (error) {
    setCaptureState("idle");
    voiceStatusEl.textContent = "Voice failed";
    showError(`Resident voice invocation failed: ${String(error)}`);
  }
}

async function submitText(text) {
  clearError();
  appendMessage("user", text);
  setState("REASONING");
  appendPresence("reasoning");
  setStateLabel("REASONING", turnStateEl);
  sendButton.disabled = true;

  try {
    const response = JSON.parse(await invoke("submit_text", { text }));
    setStateLabel(response.final_state, turnStateEl);
    setState(response.failure_reason ? "FAILED" : response.final_state);
    if (response.failure_reason) {
      showError(response.failure_reason);
    }
    appendMessage("assistant", response.response_text || response.failure_reason);
    appendToolCalls(response.tool_calls);
    await refreshSessionStatus();
  } catch (error) {
    setStateLabel("FAILED", turnStateEl);
    showError(String(error));
  } finally {
    sendButton.disabled = false;
    inputEl.focus();
  }
}

formEl.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = inputEl.value.trim();
  if (!text) return;
  inputEl.value = "";
  submitText(text);
});

pttButton.addEventListener("click", (event) => {
  event.preventDefault();
  invokeResidentPtt();
});

personalitySelectEl.addEventListener("change", (event) => {
  selectPersonality(event.target.value).catch((error) => showError(String(error)));
});

settingsTriggerEl.addEventListener("click", () => {
  if (settingsPanelEl.hidden) {
    openSettings(settingsPanelEl, {
      getOperatorConfig: async () => JSON.parse(await invoke("get_operator_config")),
      writeOperatorConfig: async (fields) => JSON.parse(await invoke("write_operator_config", { fields })),
      restartBackend: restartBackendForSettings,
      onRestartRequiredChange: updateSettingsRestartRequired,
    }).catch((error) => showError(String(error)));
    return;
  }
  closeSettings();
});

if (wakeToggleEl) {
  wakeToggleEl.addEventListener("click", () => {
    invoke("toggle_wake_monitor")
      .then((payload) => {
        const status = JSON.parse(payload);
        renderWakeStatus(status, wakeIndicatorEl);
        wakeToggleEl.disabled = !status.available;
        wakeToggleEl.textContent = status.active || status.monitoring ? "Stop" : "Start";
        wakeToggleEl.setAttribute("aria-pressed", status.active || status.monitoring ? "true" : "false");
      })
      .catch((error) => showError(String(error)));
  });
}

window.addEventListener("beforeunload", () => {
  stopWakePolling();
  stopSessionPolling();
  invoke("stop_wake_monitor").catch(() => undefined);
  invoke("stop_backend").catch(() => undefined);
});

async function startApp() {
  applyStored();
  await startDesktop();
  initAppearanceControls(appearanceControlsEl);
}

startApp();
