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
let mediaStream = null;
let mediaRecorder = null;
let audioChunks = [];
let activePersonalityId = "default";

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
    `transcript: ${result.transcript ?? ""}`,
    `response: ${result.response_text ?? ""}`,
    `final_state: ${result.final_state ?? ""}`,
    `failure_reason: ${result.failure_reason ?? ""}`,
    `tts_degraded: ${Boolean(result.tts_degraded)}`,
    `tts_degraded_reason: ${result.tts_degraded_reason ?? ""}`,
    `interrupted: ${Boolean(result.interrupted)}`,
    `interruption_events: ${JSON.stringify(result.interruption_events ?? [])}`,
  ];
  voiceDetailEl.textContent = lines.join("\n");
}

function setCaptureState(state) {
  pttButton.dataset.captureState = state;
  if (state === "recording") {
    pttButton.disabled = false;
    pttButton.setAttribute("aria-pressed", "true");
    pttButton.textContent = "Stop and Submit";
    voiceStatusEl.textContent = "Recording… click to submit";
    return;
  }
  if (state === "processing") {
    pttButton.disabled = true;
    pttButton.setAttribute("aria-pressed", "false");
    pttButton.textContent = "Submitting Voice…";
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
  return status;
}

async function refreshWakeStatus() {
  try {
    const status = JSON.parse(await invoke("get_wake_status"));
    renderWakeStatus(status, wakeIndicatorEl);
    return status;
  } catch (error) {
    renderWakeStatus(
      {
        provider: "unknown",
        available: false,
        monitoring: false,
        reason: `Wake status unavailable; PTT-only fallback is active. Reason: ${String(error)}`,
      },
      wakeIndicatorEl,
    );
    return null;
  }
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
    await refreshWakeStatus();
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
}

function updateSettingsRestartRequired(required, details = {}) {
  if (!settingsRestartRequiredEl) return;
  settingsRestartRequiredEl.hidden = !(required && !details.panelOpen);
  settingsRestartRequiredEl.textContent = required ? "Restart required" : "";
}

async function blobToAudioBuffer(blob) {
  const arrayBuffer = await blob.arrayBuffer();
  const audioContext = new AudioContext();
  try {
    return await audioContext.decodeAudioData(arrayBuffer);
  } finally {
    await audioContext.close();
  }
}

function encodeWav(audioBuffer) {
  const sampleRate = audioBuffer.sampleRate;
  const channelData = audioBuffer.getChannelData(0);
  const dataSize = channelData.length * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  writeAscii(view, 0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeAscii(view, 8, "WAVE");
  writeAscii(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeAscii(view, 36, "data");
  view.setUint32(40, dataSize, true);

  let offset = 44;
  for (const sample of channelData) {
    const clamped = Math.max(-1, Math.min(1, sample));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += 2;
  }
  return new Uint8Array(buffer);
}

function writeAscii(view, offset, value) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

async function startVoiceCapture() {
  if (pttButton.dataset.captureState !== "idle") return;
  clearError();
  if (!navigator.mediaDevices?.getUserMedia) {
    showError("Microphone capture is unavailable in this WebView.");
    voiceStatusEl.textContent = "Voice failed";
    setCaptureState("idle");
    return;
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioChunks = [];
    mediaRecorder = new MediaRecorder(mediaStream);
    mediaRecorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) audioChunks.push(event.data);
    });
    mediaRecorder.addEventListener("stop", handleVoiceCaptureStop, { once: true });
    mediaRecorder.start();
    setCaptureState("recording");
    setState("LISTENING");
    appendPresence("listening");
  } catch (error) {
    setCaptureState("idle");
    voiceStatusEl.textContent = "Voice failed";
    showError(`Microphone permission/capture failed: ${String(error)}`);
  }
}

function stopVoiceCapture() {
  if (pttButton.dataset.captureState !== "recording") return;
  if (mediaRecorder && mediaRecorder.state !== "inactive") {
    setCaptureState("processing");
    voiceStatusEl.textContent = "Encoding WAV…";
    appendPresence("transcribing");
    mediaRecorder.stop();
    return;
  }
  setCaptureState("idle");
  voiceStatusEl.textContent = "Voice failed";
  showError("Voice capture was not active.");
}

async function handleVoiceCaptureStop() {
  try {
    for (const track of mediaStream?.getTracks() || []) track.stop();
    const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
    const audioBuffer = await blobToAudioBuffer(audioBlob);
    const wavBytes = encodeWav(audioBuffer);
    voiceStatusEl.textContent = `Posting WAV (${wavBytes.byteLength} bytes)…`;
    appendPresence("reasoning");
    const response = JSON.parse(await invoke("submit_voice", { audioBytes: Array.from(wavBytes) }));
    setVoiceDetail(response);
    setStateLabel(response.final_state, turnStateEl);
    setState(response.failure_reason ? "FAILED" : response.final_state, response.tts_degraded);
    if (response.failure_reason || response.tts_degraded) {
      const reason = response.failure_reason || response.tts_degraded_reason || "Voice turn degraded.";
      showError(reason);
    }
    appendMessage("user", response.transcript || "(voice transcript unavailable)");
    appendMessage("assistant", response.response_text || response.failure_reason || response.tts_degraded_reason);
    voiceStatusEl.textContent = "Voice complete";
  } catch (error) {
    voiceStatusEl.textContent = "Voice failed";
    showError(`Voice turn failed: ${String(error)}`);
  } finally {
    mediaStream = null;
    mediaRecorder = null;
    audioChunks = [];
    setCaptureState("idle");
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
  const captureState = pttButton.dataset.captureState || "idle";
  if (captureState === "idle") {
    startVoiceCapture();
    return;
  }
  if (captureState === "recording") {
    stopVoiceCapture();
  }
});

personalitySelectEl.addEventListener("change", (event) => {
  selectPersonality(event.target.value).catch((error) => showError(String(error)));
});

settingsTriggerEl.addEventListener("click", () => {
  if (settingsPanelEl.hidden) {
    openSettings(settingsPanelEl, {
      restartBackend: restartBackendForSettings,
      onRestartRequiredChange: updateSettingsRestartRequired,
    }).catch((error) => showError(String(error)));
    return;
  }
  closeSettings();
});

window.addEventListener("beforeunload", () => {
  invoke("stop_backend").catch(() => undefined);
});

async function startApp() {
  applyStored();
  await startDesktop();
  initAppearanceControls(appearanceControlsEl);
}

startApp();
