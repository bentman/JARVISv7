import { createApiClient } from "./api-client.js";
import { applyStored } from "./components/appearance-controls.js";
import { clearBackendDiagnostics, renderBackendDiagnostics } from "./components/backend-diagnostics.js";
import { renderConversationDebug } from "./components/conversation-debug.js";
import { renderDegradedList, selectedFamilyBlockers } from "./components/degraded-list.js";
import { renderReadiness as renderReadinessPanel } from "./components/readiness-panel.js";
import { createResidentVoicePresenter } from "./components/resident-voice.js";
import { renderServiceStatus } from "./components/service-status.js";
import { clearRestartRequired, closeSettings, markRestartRequired, openSettings, restartRequiredScopes } from "./components/settings-panel.js";
import { closeProviderSettings, openProviderSettings, providerSettingsOpen } from "./components/llm-provider-settings.js";
import { createMemoryPanel } from "./components/memory-panel.js";
import { createActionsPanel } from "./components/actions-panel.js";
import { createExtensionsPanel } from "./components/extensions-panel.js";
import { createAgentsPanel, createHandoffStatus } from "./components/agents-panel.js";
import { errorMessage } from "./components/ui/format.js";
import { createAdvancedPanelCoordinator } from "./components/advanced-panel.js";
import { createDesktopState } from "./components/desktop-state.js";
import { renderWakeStatus } from "./components/wake-indicator.js";
import { createDesktopPolling } from "./components/desktop-polling.js";
import { createSearchStatus } from "./components/search-evidence.js";
import { createConversation } from "./components/conversation.js";

const healthEl = document.querySelector("#backend-health");
const sessionEl = document.querySelector("#session-id");
const turnCountEl = document.querySelector("#session-turn-count");
const wakeIndicatorEl = document.querySelector("#wake-indicator");
const wakeToggleEl = document.querySelector("#wake-toggle");
const residentModeEl = document.querySelector("#resident-mode");
const residentTtsVoiceEl = document.querySelector("#resident-tts-voice");
const residentTtsVoiceHintEl = document.querySelector("#resident-tts-voice-hint");
const residentStatusEl = document.querySelector("#resident-voice-status");
const personalityCurrentEl = document.querySelector("#personality-current");
const personalitySelectEl = document.querySelector("#personality-select");
const personalityDetailEl = document.querySelector("#personality-detail");
const settingsRestartRequiredEl = document.querySelector("#settings-restart-required");
const settingsPanelEl = document.querySelector("#settings-panel");
const providersPanelEl = document.querySelector("#providers-panel");
const memoryPanelEl = document.querySelector("#memory-panel");
const actionsPanelEl = document.querySelector("#actions-panel");
const extensionsPanelEl = document.querySelector("#extensions-panel");
const agentsPanelEl = document.querySelector("#agents-panel");
const advancedTriggerEl = document.querySelector("#advanced-controls-trigger");
const advancedDialogEl = document.querySelector("#advanced-panel");
const advancedRailEl = document.querySelector("#advanced-panel-rail");
const advancedCloseEl = document.querySelector("#advanced-panel-close");
const advancedDetailEl = document.querySelector(".advanced-panel-detail");
const readinessEl = document.querySelector("#readiness-panel");
const degradedEl = document.querySelector("#degraded-conditions");
const serviceStatusEl = document.querySelector("#service-status");
const errorEl = document.querySelector("#error-panel");
const errorActionsEl = document.querySelector("#error-actions");
const retryStartButton = document.querySelector("#retry-start-backend");
const logEl = document.querySelector("#conversation-log");
const turnStatusAnchorEl = document.querySelector("#turn-status-anchor");
const formEl = document.querySelector("#text-form");
const inputEl = document.querySelector("#text-input");
const sendButton = document.querySelector("#send-button");
const pttButton = document.querySelector("#ptt-button");
const voiceStatusEl = document.querySelector("#voice-status");
const voiceDetailEl = document.querySelector("#voice-detail");
const backendDiagnosticsEl = document.querySelector("#backend-diagnostics");

const invoke = window.__TAURI__?.core?.invoke;
const api = createApiClient(invoke);
const searchStatus = createSearchStatus({
  label: document.querySelector("#search-status"),
  stopButton: document.querySelector("#search-stop"),
  cancelSearch: (sessionId, turnId) => api.cancelSearch(sessionId, turnId),
  onError: (error) => showError(String(error)),
});
const handoffStatus = createHandoffStatus({
  label: document.querySelector("#handoff-status"),
  endButton: document.querySelector("#handoff-end"),
  openButton: document.querySelector("#handoff-open"),
  openAgent: (profileId) => openAdvancedFocused("agents", () => agentsPanel.controller.selectAgent(profileId)),
  endHandoff: (sessionId) => api.endHandoff(sessionId),
  onEnded: () => refreshSessionStatus(),
  onError: (error) => showError(String(error)),
});
const memoryPanel = createMemoryPanel(
  memoryPanelEl,
  {
    getMemoryPolicy: (...args) => api.getMemoryPolicy(...args),
    getMemoryLayers: (...args) => api.getMemoryLayers(...args),
    getArtifactRetentionPolicy: (...args) => api.getArtifactRetentionPolicy(...args),
    updateMemoryPolicy: (...args) => api.updateMemoryPolicy(...args),
    listMemories: (...args) => api.listMemories(...args),
    getMemoryDetail: (...args) => api.getMemoryDetail(...args),
    confirmMemory: (...args) => api.confirmMemory(...args),
    correctMemory: (...args) => api.correctMemory(...args),
    disputeMemory: (...args) => api.disputeMemory(...args),
    forgetMemory: (...args) => api.forgetMemory(...args),
    getMemoryCurationStatus: (...args) => api.getMemoryCurationStatus(...args),
  },
  { onClose: () => advancedPanel.requestClose() },
);

const actionsPanel = createActionsPanel(
  actionsPanelEl,
  {
    getActionCapabilities: (...args) => api.getActionCapabilities(...args),
    getPendingActions: (...args) => api.getPendingActions(...args),
    getActionAudit: (...args) => api.getActionAudit(...args),
    getActionStatus: (...args) => api.getActionStatus(...args),
    proposeAction: (...args) => api.proposeAction(...args),
    decideAction: (...args) => api.decideAction(...args),
    cancelAction: (...args) => api.cancelAction(...args),
  },
  { onClose: () => advancedPanel.requestClose() },
);

const extensionsPanel = createExtensionsPanel(
  extensionsPanelEl,
  {
    getExtensions: (...args) => api.getExtensions(...args),
    getExtensionErrors: (...args) => api.getExtensionErrors(...args),
    getExtensionDetail: (...args) => api.getExtensionDetail(...args),
    getExtensionBody: (...args) => api.getExtensionBody(...args),
    getExtensionDefinition: (...args) => api.getExtensionDefinition(...args),
    setExtensionState: (...args) => api.setExtensionState(...args),
    getExtensionRuntime: (...args) => api.getExtensionRuntime(...args),
    getExtensionRuns: (...args) => api.getExtensionRuns(...args),
    invokeExtension: (...args) => api.invokeExtension(...args),
    answerExtensionInput: (...args) => api.answerExtensionInput(...args),
    writeExtensionCredential: (...args) => api.writeExtensionCredential(...args),
    proposeAction: (...args) => api.proposeAction(...args),
    getExtensionOauth: (...args) => api.getExtensionOauth(...args),
    startExtensionOauth: (...args) => api.startExtensionOauth(...args),
    completeExtensionOauth: (...args) => api.completeExtensionOauth(...args),
    forgetExtensionOauth: (...args) => api.forgetExtensionOauth(...args),
    disconnectExtension: (...args) => api.disconnectExtension(...args),
    decideAction: (...args) => api.decideAction(...args),
    cancelAction: (...args) => api.cancelAction(...args),
  },
  { onClose: () => advancedPanel.requestClose() },
);
let activePersonalityId = "default";
let desktopState = null;
let personalitySelectionPending = false;
const PERSONALITY_STORAGE_KEY = "jarvisv7_active_personality";
const TTS_VOICE_STORAGE_KEY = "jarvisv7_active_tts_voice";
const RESIDENT_VOICE_MODE_STORAGE_KEY = "jarvisv7_active_resident_voice_mode";
let ttsVoicePreferenceRestored = false;
let residentVoiceModePreferenceRestored = false;

const agentsPanel = createAgentsPanel(
  agentsPanelEl,
  {
    listAgents: (...args) => api.listAgents(...args),
    listAgentRuns: (...args) => api.listAgentRuns(...args),
    listAgentTools: (...args) => api.listAgentTools(...args),
    invokeAgent: (...args) => api.invokeAgent(...args),
    cancelAgent: (...args) => api.cancelAgent(...args),
    createAgent: (...args) => api.createAgent(...args),
    updateAgent: (...args) => api.updateAgent(...args),
    deleteAgent: (...args) => api.deleteAgent(...args),
    setExtensionState: (...args) => api.setExtensionState(...args),
    getExtensions: (...args) => api.getExtensions(...args),
    getExtensionRuntime: (...args) => api.getExtensionRuntime(...args),
    getExtensionRuns: (...args) => api.getExtensionRuns(...args),
    invokeExtension: (...args) => api.invokeExtension(...args),
    answerExtensionInput: (...args) => api.answerExtensionInput(...args),
    getPendingActions: (...args) => api.getPendingActions(...args),
    decideAction: (...args) => api.decideAction(...args),
    cancelAction: (...args) => api.cancelAction(...args),
  },
  { onClose: () => advancedPanel.requestClose() },
);

const advancedPanel = createAdvancedPanelCoordinator({
  dismiss: () => closeAdvancedDialog(),
  categories: [
    {
      id: "providers",
      isOpen: () => providerSettingsOpen(),
      open: () =>
        openProviderSettings(providersPanelEl, {
          handlers: {
            getLlmConfig: api.getLlmConfig,
            createLlmProfile: api.createLlmProfile,
            updateLlmProfile: api.updateLlmProfile,
            deleteLlmProfile: api.deleteLlmProfile,
            testLlmProfile: api.testLlmProfile,
            updateLlmSelection: api.updateLlmSelection,
            rotateSecretStoreKey: api.rotateSecretStoreKey,
          },
          restartBackend: restartBackendForSettings,
          restartRequiredScopes,
          markRestartRequired,
          clearRestartRequired,
          onClose: () => advancedPanel.requestClose(),
        }),
      close: () => closeProviderSettings(),
    },
    {
      id: "settings",
      isOpen: () => !settingsPanelEl.hidden,
      open: () =>
        openSettings(settingsPanelEl, {
          getOperatorConfig: api.getOperatorConfig,
          writeOperatorConfig: api.writeOperatorConfig,
          restartBackend: restartBackendForSettings,
          onRestartRequiredChange: updateSettingsRestartRequired,
        }),
      close: () => closeSettings(),
    },
    { id: "memory", isOpen: () => memoryPanel.isOpen(), open: () => memoryPanel.open(), close: () => memoryPanel.close() },
    { id: "actions", isOpen: () => actionsPanel.isOpen(), open: () => actionsPanel.open(), close: () => actionsPanel.close() },
    { id: "extensions", isOpen: () => extensionsPanel.isOpen(), open: () => extensionsPanel.open(), close: () => extensionsPanel.close() },
    { id: "agents", isOpen: () => agentsPanel.isOpen(), open: () => agentsPanel.open(), close: () => agentsPanel.close() },
  ],
});

let lastAdvancedCategoryId = "providers";
const advancedScrollPositions = new Map();

// The detail pane is shared by every category, so its scroll position belongs to whichever
// category is showing. It is recorded while that content is still laid out - before a switch
// and before the dialog closes, since a closed dialog reports no scroll - and restored on return.
function rememberAdvancedScroll() {
  const active = advancedPanel.activeCategoryId();
  if (active && advancedDetailEl) advancedScrollPositions.set(active, advancedDetailEl.scrollTop);
}

function closeAdvancedDialog() {
  rememberAdvancedScroll();
  advancedDialogEl.close();
}

function renderAdvancedRail() {
  const active = advancedPanel.activeCategoryId();
  for (const button of advancedRailEl.querySelectorAll("button[data-category]")) {
    button.setAttribute("aria-selected", button.dataset.category === active ? "true" : "false");
    const category = button.dataset.category;
    if (category === "settings") {
      let badge = button.querySelector(".rail-badge");
      const needsRestart = restartRequiredScopes().length > 0;
      if (needsRestart) {
        if (!badge) {
          badge = document.createElement("span");
          badge.className = "rail-badge badge-warning";
          button.appendChild(badge);
        }
        badge.textContent = "Restart";
      } else if (badge) {
        badge.remove();
      }
    }
  }
}

async function openAdvancedCategory(categoryId) {
  rememberAdvancedScroll();
  const opened = await advancedPanel.openCategory(categoryId);
  if (opened) {
    lastAdvancedCategoryId = opened;
    if (advancedDetailEl) advancedDetailEl.scrollTop = advancedScrollPositions.get(opened) || 0;
  }
  renderAdvancedRail();
  return opened;
}

// Opens Advanced Controls on one category, then points that panel at the item the operator
// followed a link for.
async function openAdvancedFocused(categoryId, focus) {
  if (!advancedDialogEl.open) {
    advancedDialogEl.showModal();
    updateSettingsRestartRequired(restartRequiredScopes().length > 0);
  }
  try {
    if (await openAdvancedCategory(categoryId)) await focus();
  } catch (error) {
    showError(errorMessage(error));
  }
}

const presenceByProfile = {
  default: { listening: "Listening.", transcribing: "Transcribing.", reasoning: "Understood." },
  concise: { listening: "Listening.", transcribing: "Transcribing.", reasoning: "On it." },
  warm: { listening: "Go ahead.", transcribing: "I’m transcribing that.", reasoning: "I’m on it." },
};

function setState(value, degraded = false) {
  desktopState?.renderSystemState(value, degraded);
  document.body.dataset.degraded = degraded ? "true" : "false";
}

function showError(message, systemState = null) {
  desktopState.showError(message, systemState);
  if (systemState) document.body.dataset.degraded = "false";
  if (errorActionsEl) {
    if (systemState === "BACKEND_UNAVAILABLE") errorActionsEl.classList.remove("hidden");
    else errorActionsEl.classList.add("hidden");
  }
}

function clearError() {
  desktopState.clearError();
  if (errorActionsEl) errorActionsEl.classList.add("hidden");
}

const personalityNames = new Map();
const conversation = createConversation({
  logEl,
  speakerName: (profileId) => personalityNames.get(profileId || activePersonalityId) || "JARVIS",
  openSearchSource: (url) => api.openSearchSource(url),
  onError: (error) => showError(errorMessage(error)),
  onOpenAction: (proposalId) => openAdvancedFocused("actions", () => actionsPanel.controller.selectProposal(proposalId)),
  onOpenAgent: (profileId) => openAdvancedFocused("agents", () => agentsPanel.controller.selectAgent(profileId)),
  getTurns: (after) => api.getSessionTurns(after),
  decide: async (proposalId, outcome) => {
    await api.decideAction(proposalId, outcome);
    await refreshSessionStatus();
  },
});
// A local text turn renders from its own response; the feed waits so it cannot render it twice.
let localTurnPending = false;
let lastSeenTurnCount = null;

function appendMessage(role, text) {
  conversation.note(role, text);
}

function setTextEntryEnabled(enabled) {
  sendButton.disabled = !enabled;
  inputEl.disabled = !enabled;
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
  personalityDetailEl.textContent = `Locale: ${profile.locale || "—"}  Description: ${profile.description || "—"}`;
}

function renderProfileDiagnostics(profileErrors) {
  if (!Array.isArray(profileErrors) || profileErrors.length === 0) return;
  const heading = document.createElement("div");
  heading.textContent = "Profile diagnostics";
  const rows = profileErrors.map((error) => {
    const row = document.createElement("div");
    row.textContent = `${error.profile_path || "profile"}: ${error.reason || "load failed"}`;
    return row;
  });
  personalityDetailEl.append(heading, ...rows);
}

const residentVoice = createResidentVoicePresenter({
  pttButton,
  voiceStatusEl,
  residentModeEl,
  residentStatusEl,
  setState: (state) => desktopState?.renderTurnStatus(state),
  showError,
  appendMessage,
  syncConversation: () => conversation.sync(),
});

desktopState = createDesktopState(document.querySelector(".shell"), turnStatusAnchorEl, errorEl);

function renderReadiness(readiness) {
  renderReadinessPanel(readiness, readinessEl);
  renderDegradedList(readiness, degradedEl);
  renderServiceStatus(readiness.services, serviceStatusEl);
  const selectedPathDegraded = selectedFamilyBlockers(readiness).length > 0;
  const degraded = readiness.status !== "ready" || readiness.requires_degraded_mode || selectedPathDegraded;
  desktopState.renderSystemState(degraded ? "DEGRADED" : "READY", degraded);
}

function renderSessionStatus(status) {
  sessionEl.textContent = status.session_id || "not active";
  if (turnCountEl) turnCountEl.textContent = String(status.turn_count ?? 0);
  conversation.renderPending(status.pending_approval || null);
  if (!localTurnPending && status.turn_count !== lastSeenTurnCount) {
    lastSeenTurnCount = status.turn_count;
    conversation.sync();
  }
  renderConversationDebug(status, voiceDetailEl);
  residentVoice.renderResidentVoiceStatus(status);
  if (desktopState) desktopState.renderTurnStatus(status.state);
  searchStatus.render(status.active_search);
  handoffStatus.render(status);
  return status;
}

async function refreshSessionStatus() {
  return renderSessionStatus(await api.getSessionStatus());
}

function renderResidentVoiceUnavailable(error) {
  residentVoice.renderResidentModeStatus({
    mode: "ptt-only",
    available: false,
    vad_configured: false,
    barge_in_supported: false,
    barge_in_wired: false,
    degraded_reasons: [`resident voice status unavailable: ${String(error)}`],
    stream: { present: false, running: false, subscribers: 0, buffer_chunks: 0, dropped_chunks: 0, last_error: null },
  });
  renderResidentTtsVoiceSelector({ tts_voice: "", tts_supported_voices: [], tts_voice_restart_required: false });
}

async function refreshResidentVoiceStatus() {
  if (!api?.getResidentVoiceStatus) return null;
  try {
    let status = await api.getResidentVoiceStatus();
    status = await applyStoredResidentVoiceModeIfAvailable(status);
    status = await applyStoredTtsVoiceIfAvailable(status);
    residentVoice.renderResidentModeStatus(status);
    renderResidentTtsVoiceSelector(status);
    return status;
  } catch (error) {
    renderResidentVoiceUnavailable(error);
    return null;
  }
}

function renderResidentTtsVoiceSelector(status) {
  if (!residentTtsVoiceEl) return;
  const voices = Array.isArray(status.tts_supported_voices) ? status.tts_supported_voices : [];
  const currentVoice = status.tts_voice || "";
  residentTtsVoiceEl.replaceChildren();
  if (voices.length === 0) {
    const option = document.createElement("option");
    option.value = "";
    option.textContent = currentVoice || "unavailable";
    residentTtsVoiceEl.appendChild(option);
    residentTtsVoiceEl.disabled = true;
  } else {
    for (const voice of voices) {
      const option = document.createElement("option");
      option.value = voice;
      option.textContent = voice;
      option.selected = voice === currentVoice;
      residentTtsVoiceEl.appendChild(option);
    }
    residentTtsVoiceEl.value = voices.includes(currentVoice) ? currentVoice : voices[0];
    residentTtsVoiceEl.disabled = false;
  }
  if (residentTtsVoiceHintEl) {
    residentTtsVoiceHintEl.textContent = "Selected voice is saved locally and applies to runtime.";
  }
}

async function setResidentTtsVoice(voice, options = {}) {
  if (!api?.setResidentVoiceTtsVoice) return null;
  clearError();
  const status = await api.setResidentVoiceTtsVoice(voice);
  residentVoice.renderResidentModeStatus(status);
  renderResidentTtsVoiceSelector(status);
  if (options.persist !== false && status.tts_voice) {
    window.localStorage?.setItem(TTS_VOICE_STORAGE_KEY, status.tts_voice);
  }
  return status;
}

async function applyStoredResidentVoiceModeIfAvailable(status) {
  if (residentVoiceModePreferenceRestored) return status;
  residentVoiceModePreferenceRestored = true;
  let storedMode = window.localStorage?.getItem(RESIDENT_VOICE_MODE_STORAGE_KEY);
  if (storedMode === null) {
    storedMode = "ptt+wake";
  }
  const modes = ["ptt-only", "ptt+wake", "hands-free", "continuous"];
  if (!modes.includes(storedMode)) {
    window.localStorage?.removeItem(RESIDENT_VOICE_MODE_STORAGE_KEY);
    return status;
  }
  if (storedMode === status.mode) return status;
  return (await setResidentVoiceMode(storedMode, { persist: false })) || status;
}

async function applyStoredTtsVoiceIfAvailable(status) {
  if (ttsVoicePreferenceRestored) return status;
  ttsVoicePreferenceRestored = true;
  const storedVoice = window.localStorage?.getItem(TTS_VOICE_STORAGE_KEY);
  if (!storedVoice) return status;
  const voices = Array.isArray(status.tts_supported_voices) ? status.tts_supported_voices : [];
  if (!voices.includes(storedVoice)) {
    window.localStorage?.removeItem(TTS_VOICE_STORAGE_KEY);
    return status;
  }
  if (storedVoice === status.tts_voice) return status;
  return (await setResidentTtsVoice(storedVoice, { persist: false })) || status;
}

async function ensureResidentVoiceStream() {
  if (!api?.startResidentVoiceStream) return refreshResidentVoiceStatus();
  const current = await refreshResidentVoiceStatus();
  if (current?.stream?.running || current?.stream_running) return current;
  const started = await api.startResidentVoiceStream();
  residentVoice.renderResidentModeStatus(started);
  renderResidentTtsVoiceSelector(started);
  return started;
}

async function setResidentVoiceMode(mode, options = {}) {
  if (!api?.setResidentVoiceMode) return null;
  clearError();
  if (mode !== "ptt-only") {
    await ensureResidentVoiceStream();
  }
  const status = await api.setResidentVoiceMode(mode);
  residentVoice.renderResidentModeStatus(status);
  renderResidentTtsVoiceSelector(status);
  if (options.persist !== false && status.mode) {
    window.localStorage?.setItem(RESIDENT_VOICE_MODE_STORAGE_KEY, status.mode);
  }
  if (mode === "ptt+wake") {
    await startWakeMonitorIfAvailable();
  } else {
    await refreshWakeStatus();
  }
  await refreshSessionStatus();
  return status;
}

function renderWakeStatusPayload(status) {
  renderWakeStatus(status, wakeIndicatorEl);
  if (wakeToggleEl) {
    wakeToggleEl.disabled = !status.available;
    wakeToggleEl.textContent = status.active || status.monitoring ? "Stop" : "Start";
    wakeToggleEl.setAttribute("aria-pressed", status.active || status.monitoring ? "true" : "false");
  }
  return status;
}

function renderWakeUnavailable(error) {
  return renderWakeStatusPayload({
    provider: "unknown",
    available: false,
    monitoring: false,
    active: false,
    enabled: false,
    reason: `Wake status unavailable; PTT-only fallback is active. Reason: ${String(error)}`,
  });
}

async function refreshWakeStatus() {
  try {
    return renderWakeStatusPayload(await api.getWakeStatus());
  } catch (error) {
    renderWakeUnavailable(error);
    return null;
  }
}

async function refreshDesktopStatus() {
  try {
    const snapshot = await api.getDesktopStatus();
    renderSessionStatus(snapshot.session);
    residentVoice.renderResidentModeStatus(snapshot.resident_voice);
    renderResidentTtsVoiceSelector(snapshot.resident_voice);
    renderWakeStatusPayload(snapshot.wake);
    return snapshot.session;
  } catch (error) {
    renderResidentVoiceUnavailable(error);
    renderWakeUnavailable(error);
    throw error;
  }
}

async function startWakeMonitorIfAvailable() {
  const status = await refreshWakeStatus();
  if (!status?.available || status.active || status.monitoring) return status;
  const started = await api.startWakeMonitor();
  renderWakeStatus(started, wakeIndicatorEl);
  if (wakeToggleEl) {
    wakeToggleEl.disabled = !started.available;
    wakeToggleEl.textContent = started.active || started.monitoring ? "Stop" : "Start";
    wakeToggleEl.setAttribute("aria-pressed", started.active || started.monitoring ? "true" : "false");
  }
  return started;
}

async function refreshPersonalityProfiles() {
  const payload = await api.getPersonalityList();
  activePersonalityId = payload.active_profile_id || "default";
  let selectedProfile = null;
  personalitySelectEl.replaceChildren();
  for (const profile of payload.profiles || []) {
    personalityNames.set(profile.profile_id, profile.display_name || profile.profile_id);
    const option = document.createElement("option");
    option.value = profile.profile_id;
    option.textContent = `${profile.display_name} (${profile.profile_id})`;
    option.selected = profile.profile_id === activePersonalityId;
    personalitySelectEl.appendChild(option);
    if (option.selected) selectedProfile = profile;
  }
  if (selectedProfile) updatePersonalityDisplay(selectedProfile);
  personalitySelectEl.value = activePersonalityId;
  renderProfileDiagnostics(payload.profile_errors);
  personalitySelectEl.disabled = false;
  return payload;
}

async function selectPersonality(profileId) {
  personalitySelectionPending = true;
  setTextEntryEnabled(false);
  personalitySelectEl.disabled = true;
  try {
    const before = await refreshSessionStatus();
    const payload = await api.selectPersonality(profileId);
    updatePersonalityDisplay(payload.active);
    window.localStorage?.setItem(PERSONALITY_STORAGE_KEY, payload.active.profile_id);
    const after = await refreshSessionStatus();
    appendMessage("system", `Personality switched to ${payload.active.profile_id}; applies to the next turn. Session preserved: ${before.session_id === after.session_id}.`);
  } finally {
    personalitySelectionPending = false;
    personalitySelectEl.disabled = false;
    setTextEntryEnabled(true);
    inputEl.focus();
  }
}

async function applyStoredPersonalityIfAvailable(profilePayload) {
  const storedProfileId = window.localStorage?.getItem(PERSONALITY_STORAGE_KEY);
  if (!storedProfileId || storedProfileId === activePersonalityId) return profilePayload;
  const available = (profilePayload.profiles || []).some((profile) => profile.profile_id === storedProfileId);
  if (!available) return profilePayload;
  await selectPersonality(storedProfileId);
  setTextEntryEnabled(false);
  return api.getPersonalityList();
}

const polling = createDesktopPolling({
  refreshSessionStatus,
  refreshDesktopStatus,
});

const { startAllPolling, stopAllPolling } = polling;

async function completeBackendStart(startPayload) {
  renderBackendDiagnostics(startPayload.diagnostics, backendDiagnosticsEl);
  sessionEl.textContent = startPayload.session_id || "created";
  if (turnCountEl) turnCountEl.textContent = String(startPayload.turn_count ?? 0);
  healthEl.textContent = "ok";
  await ensureResidentVoiceStream();
  const readiness = await api.getReadiness();
  renderReadiness(readiness);
  startAllPolling();
}

async function startDesktop() {
  clearError();
  clearBackendDiagnostics(backendDiagnosticsEl);
  setState("STARTING");
  healthEl.textContent = "starting";
  sendButton.disabled = true;
  inputEl.disabled = true;
  pttButton.disabled = true;

  if (!api) {
    showError("Tauri command bridge is unavailable; desktop backend lifecycle cannot start.", "BACKEND_UNAVAILABLE");
    healthEl.textContent = "error";
    return;
  }

  try {
    const startPayload = await api.startBackend();
    await completeBackendStart(startPayload);
    let personalityPayload = await refreshPersonalityProfiles();
    personalityPayload = await applyStoredPersonalityIfAvailable(personalityPayload);
    personalityPayload = await refreshPersonalityProfiles();
    await conversation.sync();
    appendMessage("system", "Backend started and readiness loaded.");
    appendMessage("system", `Active personality confirmed: ${personalityPayload.active_profile_id || activePersonalityId}.`);
    setTextEntryEnabled(true);
    pttButton.disabled = false;
    inputEl.focus();
  } catch (error) {
    healthEl.textContent = "error";
    renderBackendDiagnostics(error.diagnostics || { failure: String(error) }, backendDiagnosticsEl);
    showError(error.message || String(error), "BACKEND_UNAVAILABLE");
  }
}

async function restartBackendForSettings() {
  await api.stopBackend();
  setState("STARTING");
  healthEl.textContent = "starting";
  ttsVoicePreferenceRestored = false;
  residentVoiceModePreferenceRestored = false;
  const startPayload = await api.startBackend();
  await completeBackendStart(startPayload);
}

function updateSettingsRestartRequired(required) {
  if (!settingsRestartRequiredEl) return;
  // The badge stands in for the advanced-control surface while it is dismissed; with the surface
  // open the mounted category shows its own restart state.
  settingsRestartRequiredEl.hidden = !(required && !advancedDialogEl.open);
  settingsRestartRequiredEl.textContent = required ? "Restart required" : "";
}

async function invokeResidentPtt() {
  if (pttButton.dataset.captureState !== "idle") return;
  clearError();
  residentVoice.setCaptureState("processing");
  voiceStatusEl.textContent = "PTT invoked";
  desktopState?.setPendingState("LISTENING");
  appendPresence("listening");
  try {
    const status = await api.invokeResidentPtt();
    residentVoice.renderResidentVoiceStatus(status);
    await refreshSessionStatus();
  } catch (error) {
    residentVoice.setCaptureState("idle");
    voiceStatusEl.textContent = "Voice failed";
    showError(`Resident voice invocation failed: ${String(error)}`);
  }
}

async function submitText(text) {
  if (personalitySelectionPending) {
    appendMessage("system", "Profile selection is still applying; try again once it is confirmed.");
    if (!inputEl.value) inputEl.value = text;
    return;
  }
  clearError();
  appendMessage("user", text);
  desktopState?.setPendingState("REASONING");
  appendPresence("reasoning");
  sendButton.disabled = true;
  localTurnPending = true;

  try {
    const response = await api.submitText(text);
    desktopState?.renderTurnStatus(response.failure_reason ? "FAILED" : response.final_state);
    if (response.failure_reason) {
      showError(response.failure_reason);
    }
    conversation.renderTurn(
      {
        ...response,
        transcript: text,
        input_modality: "text",
        personality_profile_id: response.active_personality_profile_id,
      },
      { transcriptShown: true },
    );
    localTurnPending = false;
    await refreshSessionStatus();
  } catch (error) {
    desktopState?.renderTurnStatus("FAILED");
    showError(errorMessage(error));
    if (!inputEl.value) {
      inputEl.value = text;
    }
  } finally {
    localTurnPending = false;
    sendButton.disabled = personalitySelectionPending;
    inputEl.focus();
  }
}

const promptHistory = [];
let promptHistoryIndex = -1;
let promptHistoryDraft = "";

inputEl.addEventListener("keydown", (event) => {
  if (event.key === "ArrowUp") {
    if (!promptHistory.length) return;
    if (promptHistoryIndex === -1 && inputEl.selectionStart !== 0 && inputEl.value) return;
    if (promptHistoryIndex === -1) {
      promptHistoryDraft = inputEl.value;
      promptHistoryIndex = promptHistory.length - 1;
    } else if (promptHistoryIndex > 0) {
      promptHistoryIndex -= 1;
    }
    inputEl.value = promptHistory[promptHistoryIndex];
    event.preventDefault();
  } else if (event.key === "ArrowDown") {
    if (promptHistoryIndex === -1) return;
    if (promptHistoryIndex < promptHistory.length - 1) {
      promptHistoryIndex += 1;
      inputEl.value = promptHistory[promptHistoryIndex];
    } else {
      promptHistoryIndex = -1;
      inputEl.value = promptHistoryDraft;
    }
    event.preventDefault();
  }
});

inputEl.addEventListener("input", () => {
  if (promptHistoryIndex !== -1 && inputEl.value !== promptHistory[promptHistoryIndex]) {
    promptHistoryIndex = -1;
  }
});

formEl.addEventListener("submit", (event) => {
  event.preventDefault();
  if (personalitySelectionPending) {
    appendMessage("system", "Profile selection is still applying; wait for confirmation before sending.");
    return;
  }
  const text = inputEl.value.trim();
  if (!text) return;
  if (!promptHistory.length || promptHistory[promptHistory.length - 1] !== text) {
    promptHistory.push(text);
  }
  promptHistoryIndex = -1;
  promptHistoryDraft = "";
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

if (residentModeEl) {
  residentModeEl.addEventListener("change", (event) => {
    setResidentVoiceMode(event.target.value).catch((error) => {
      showError(String(error));
      refreshResidentVoiceStatus().catch(() => undefined);
    });
  });
}

if (residentTtsVoiceEl) {
  residentTtsVoiceEl.addEventListener("change", () => {
    setResidentTtsVoice(residentTtsVoiceEl.value).catch((error) => showError(String(error)));
  });
}

advancedTriggerEl.addEventListener("click", () => {
  advancedDialogEl.showModal();
  updateSettingsRestartRequired(restartRequiredScopes().length > 0);
  openAdvancedCategory(lastAdvancedCategoryId).catch((error) => showError(String(error)));
});

advancedCloseEl.addEventListener("click", () => closeAdvancedDialog());
// Escape closes a modal dialog natively; its cancel event is the last moment its content is laid out.
advancedDialogEl.addEventListener("cancel", () => rememberAdvancedScroll());

advancedDialogEl.addEventListener("click", (event) => {
  // A click reported against the dialog itself landed on the backdrop, not on panel content.
  if (event.target === advancedDialogEl) closeAdvancedDialog();
});

// showModal() gives Escape dismissal, focus containment and focus return for free; this single
// hook therefore covers Escape, the Close button and a backdrop click alike.
advancedDialogEl.addEventListener("close", () => {
  advancedPanel.closeActive();
  renderAdvancedRail();
  updateSettingsRestartRequired(restartRequiredScopes().length > 0);
});

advancedRailEl.addEventListener("click", (event) => {
  const button = event.target.closest("button[data-category]");
  if (!button) return;
  // Each panel focuses its own heading once mounted, so the rail does not claim focus itself.
  openAdvancedCategory(button.dataset.category).catch((error) => showError(String(error)));
});

if (wakeToggleEl) {
  wakeToggleEl.addEventListener("click", () => {
    api.toggleWakeMonitor()
      .then((status) => {
        renderWakeStatus(status, wakeIndicatorEl);
        wakeToggleEl.disabled = !status.available;
        wakeToggleEl.textContent = status.active || status.monitoring ? "Stop" : "Start";
        wakeToggleEl.setAttribute("aria-pressed", status.active || status.monitoring ? "true" : "false");
      })
      .catch((error) => showError(String(error)));
  });
}

if (retryStartButton) {
  retryStartButton.addEventListener("click", () => {
    clearError();
    startDesktop();
  });
}

if (settingsRestartRequiredEl) {
  settingsRestartRequiredEl.setAttribute("role", "button");
  settingsRestartRequiredEl.setAttribute("tabindex", "0");
  settingsRestartRequiredEl.title = "Click to restart backend now";
  const triggerRestart = () => {
    restartBackendForSettings().catch((error) => showError(String(error)));
  };
  settingsRestartRequiredEl.addEventListener("click", triggerRestart);
  settingsRestartRequiredEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      triggerRestart();
    }
  });
}

const systemStateCardEl = document.querySelector(".system-state-card");
if (systemStateCardEl) {
  systemStateCardEl.title = "View degraded/diagnostic details";
  systemStateCardEl.setAttribute("role", "button");
  systemStateCardEl.setAttribute("tabindex", "0");
  const openDiagnostics = () => {
    const startupState = document.getElementById("startup-state");
    const stateVal = startupState?.dataset.state;
    if (stateVal === "DEGRADED" || document.body.dataset.degraded === "true") {
      const degradedDetail = document.querySelector(".degraded-detail");
      if (degradedDetail) {
        degradedDetail.open = true;
        if (typeof degradedDetail.scrollIntoView === "function") {
          degradedDetail.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    } else if (stateVal === "FAILED" || stateVal === "BACKEND_UNAVAILABLE") {
      const backendDiag = document.querySelector(".backend-diagnostics");
      if (backendDiag) {
        backendDiag.open = true;
        if (typeof backendDiag.scrollIntoView === "function") {
          backendDiag.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      }
    }
  };
  systemStateCardEl.addEventListener("click", openDiagnostics);
  systemStateCardEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      openDiagnostics();
    }
  });
}

if (pttButton) {
  pttButton.title = "Push to talk (Ctrl+Space)";
}

window.addEventListener("keydown", (event) => {
  if (event.ctrlKey && event.code === "Space") {
    const active = document.activeElement;
    const tag = (active?.tagName || "").toUpperCase();
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || active?.isContentEditable) return;
    event.preventDefault();
    invokeResidentPtt();
  }
});

// A reload keeps the backend and its session; closing the window shuts both down natively.
window.addEventListener("beforeunload", () => {
  stopAllPolling();
});

async function startApp() {
  applyStored();
  await startDesktop();
}

startApp();
