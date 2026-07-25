import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { renderConversationDebug } from "../src/components/conversation-debug.js";
import { renderBackendDiagnostics } from "../src/components/backend-diagnostics.js";
import { collectDegradedConditions, selectedFamilyBlockers } from "../src/components/degraded-list.js";
import { createDesktopState } from "../src/components/desktop-state.js";
import { createResidentVoicePresenter } from "../src/components/resident-voice.js";
import { createDesktopPolling, sessionPollingInterval, statusPollingInterval } from "../src/components/desktop-polling.js";
import {
  createMemoryPanelController,
  createOperatorPanelCoordinator,
  curationActivityState,
  memoryActionsEnabled,
} from "../src/components/memory-panel.js";

const main = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");
const apiClient = readFileSync(new URL("../src/api-client.js", import.meta.url), "utf8");
const residentVoice = readFileSync(new URL("../src/components/resident-voice.js", import.meta.url), "utf8");
const conversationDebug = readFileSync(new URL("../src/components/conversation-debug.js", import.meta.url), "utf8");
const backendDiagnostics = readFileSync(new URL("../src/components/backend-diagnostics.js", import.meta.url), "utf8");
const desktopPolling = readFileSync(new URL("../src/components/desktop-polling.js", import.meta.url), "utf8");
const degradedList = readFileSync(new URL("../src/components/degraded-list.js", import.meta.url), "utf8");
const settingsPanel = readFileSync(new URL("../src/components/settings-panel.js", import.meta.url), "utf8");
const memoryPanel = readFileSync(new URL("../src/components/memory-panel.js", import.meta.url), "utf8");
const backend = readFileSync(new URL("../src-tauri/src/backend.rs", import.meta.url), "utf8");
const lib = readFileSync(new URL("../src-tauri/src/lib.rs", import.meta.url), "utf8");
const index = readFileSync(new URL("../src/index.html", import.meta.url), "utf8");
const desktopSource = main + apiClient + residentVoice;

assert.equal(sessionPollingInterval({ state: "reasoning" }), 100, "active sessions must retain responsive polling");
assert.equal(sessionPollingInterval({ state: "IDLE" }), 2000, "idle sessions must reduce polling churn");
assert.equal(sessionPollingInterval({ state: "reasoning" }, false), 10000, "hidden windows must throttle session polling");
assert.equal(statusPollingInterval(), 3000, "resident and wake status polling must reduce idle churn");
assert.equal(statusPollingInterval(false), 10000, "hidden windows must throttle status polling");

const originalDocument = globalThis.document;
const originalWindow = globalThis.window;
const originalDateNow = Date.now;
const scheduledPolling = [];
let visibilityHandler = null;
let now = 1000;
let sessionRefreshes = 0;
let desktopRefreshes = 0;
Date.now = () => now;
globalThis.document = {
  visibilityState: "visible",
  addEventListener(name, handler) {
    if (name === "visibilitychange") visibilityHandler = handler;
  },
};
globalThis.window = {
  setTimeout(callback, delay) {
    scheduledPolling.push({ callback, delay });
    return scheduledPolling.length;
  },
  clearTimeout() {},
};
const pollingBehavior = createDesktopPolling({
  refreshSessionStatus: async () => {
    sessionRefreshes += 1;
    return { state: "reasoning" };
  },
  refreshDesktopStatus: async () => {
    desktopRefreshes += 1;
    return { state: "reasoning" };
  },
});
pollingBehavior.startAllPolling();
await new Promise((resolve) => setImmediate(resolve));
assert.deepEqual(scheduledPolling.slice(-1).map(({ delay }) => delay), [100], "desktop statuses must share one adaptive poll timer");
assert.deepEqual([sessionRefreshes, desktopRefreshes], [0, 1]);
now += 100;
scheduledPolling.at(-1).callback();
await new Promise((resolve) => setImmediate(resolve));
assert.deepEqual([sessionRefreshes, desktopRefreshes], [1, 1], "fast ticks must request session status only");
now += 3000;
scheduledPolling.at(-1).callback();
await new Promise((resolve) => setImmediate(resolve));
assert.deepEqual([sessionRefreshes, desktopRefreshes], [1, 2], "slow status ticks must issue only the desktop snapshot request");
globalThis.document.visibilityState = "hidden";
visibilityHandler();
assert.deepEqual(scheduledPolling.slice(-1).map(({ delay }) => delay), [10000]);
globalThis.document.visibilityState = "visible";
visibilityHandler();
assert.deepEqual(scheduledPolling.slice(-1).map(({ delay }) => delay), [0]);
pollingBehavior.stopAllPolling();
globalThis.document = originalDocument;
globalThis.window = originalWindow;
Date.now = originalDateNow;

assert.ok(!main.includes("getUserMedia"), "desktop PTT must not capture WebView microphone audio");
assert.ok(!main.includes("MediaRecorder"), "desktop PTT must not record WebView microphone audio");
assert.ok(!backend.includes("/task/voice"), "backend bridge must not call legacy /task/voice");
assert.ok(backend.includes("/session/ptt"), "backend bridge must call resident /session/ptt");
assert.ok(lib.includes("invoke_resident_ptt"), "Tauri command must expose invoke_resident_ptt");
assert.ok(apiClient.includes('invoke("invoke_resident_ptt")'), "desktop API client must invoke resident PTT");
assert.ok(!backend.includes("application/octet-stream"), "desktop voice must not use raw upload bytes");
assert.ok(!backend.toLowerCase().includes("multipart"), "voice upload must not use multipart");
assert.ok(!main.toLowerCase().includes("websocket"), "desktop must not use WebSockets");
assert.ok(backend.includes("python_path_for_host"), "desktop launcher must resolve its interpreter through the platform helper");
assert.ok(backend.includes('venv_root.join("Scripts").join("python.exe")'), "desktop launcher must preserve the Windows venv interpreter path");
assert.ok(backend.includes('venv_root.join("bin").join("python")'), "desktop launcher must resolve the Linux venv interpreter path");
assert.ok(backend.includes("/session/status"), "backend bridge must call /session/status");
assert.ok(backend.includes("/status/desktop"), "backend bridge must call the consolidated desktop status endpoint");
assert.ok(lib.includes("http_client: Client"), "desktop state must own one shared HTTP client");
assert.ok(!backend.includes("Client::new()"), "backend requests must reuse the shared HTTP client");
assert.ok(backend.includes("timeout(Duration::from_millis(700))"), "startup health probes must retain their request timeout");
assert.ok(lib.includes("get_session_status"), "Tauri command must expose get_session_status");
assert.ok(apiClient.includes('invoke("get_session_status")'), "desktop API client must invoke get_session_status");
assert.ok(apiClient.includes('invoke("get_desktop_status")'), "desktop API client must invoke get_desktop_status");
assert.ok(index.includes("session-turn-count"), "desktop must display session turn count");
assert.ok(backend.includes("/status/wake"), "backend bridge must call /status/wake");
assert.ok(backend.includes("/status/resident-voice"), "backend bridge must call /status/resident-voice");
assert.ok(lib.includes("get_wake_status"), "Tauri command must expose get_wake_status");
assert.ok(lib.includes("get_resident_voice_status"), "Tauri command must expose get_resident_voice_status");
assert.ok(lib.includes("start_resident_voice_stream"), "Tauri command must expose start_resident_voice_stream");
assert.ok(lib.includes("set_resident_voice_mode"), "Tauri command must expose set_resident_voice_mode");
assert.ok(apiClient.includes('invoke("get_wake_status")'), "desktop API client must invoke get_wake_status");
assert.ok(apiClient.includes('invoke("get_resident_voice_status")'), "desktop API client must invoke get_resident_voice_status");
assert.ok(apiClient.includes('invoke("start_resident_voice_stream")'), "desktop API client must invoke start_resident_voice_stream");
assert.ok(apiClient.includes('invoke("set_resident_voice_mode"'), "desktop API client must invoke set_resident_voice_mode");
assert.ok(apiClient.includes('invoke("set_resident_voice_tts_voice"'), "desktop API client must invoke set_resident_voice_tts_voice");
assert.ok(desktopSource.includes("PTT-only fallback"), "desktop must display PTT-only fallback state");
assert.ok(index.includes("wake-indicator"), "desktop must display wake status");
assert.ok(index.includes("wake-toggle"), "desktop must expose wake toggle");
assert.ok(index.includes("resident-mode"), "desktop must expose resident voice mode control");
assert.ok(index.includes("resident-tts-voice"), "desktop must expose resident voice selector");
assert.ok(index.includes("Voice Selector"), "desktop must label resident voice selector");
assert.ok(index.includes("ptt-only"), "desktop must include PTT-only resident mode");
assert.ok(index.indexOf("resident-voice-panel") < index.indexOf("wake-monitor-panel"), "Resident Voice must render above Wake in the operator panel");
assert.ok(index.includes("hands-free"), "desktop must include hands-free resident mode");
assert.ok(index.includes("continuous"), "desktop must include continuous resident mode");
assert.ok(index.includes("resident-voice-status"), "desktop must display resident voice diagnostics");
assert.ok(index.includes("degraded-detail"), "desktop must include collapsed degraded detail surface");
assert.ok(index.includes("Degraded list detail"), "desktop degraded detail surface must use the required title");
assert.ok(index.includes("Conversation debug details"), "desktop must title the conversation debug surface correctly");
assert.ok(index.includes("Backend diagnostics"), "desktop must include collapsed backend diagnostics surface");
assert.ok(index.includes("backend-diagnostics"), "desktop must include backend diagnostics target element");
assert.ok(!index.includes("Voice debug details"), "desktop must not keep the voice-only debug label");
assert.ok(index.indexOf("Conversation debug details") < index.indexOf("Backend diagnostics"), "backend diagnostics must follow conversation debug details");
assert.ok(index.indexOf("Backend diagnostics") < index.indexOf("Degraded list detail"), "backend diagnostics must precede degraded list detail");
assert.ok(main.includes("renderConversationDebug(status, voiceDetailEl)"), "desktop must render conversation debug from session status");
assert.ok(main.includes("renderBackendDiagnostics"), "desktop must render backend diagnostics");
assert.ok(main.includes("error.diagnostics"), "startup failures must not collapse only into String(error)");
assert.ok(desktopPolling.includes("let pollTimer"), "desktop polling helper must own one consolidated timer handle");
assert.ok(desktopPolling.includes("refreshDesktopStatus"), "slow polling ticks must use the consolidated desktop snapshot");
assert.ok(!desktopPolling.includes("refreshResidentVoiceStatus"), "polling must not issue a separate resident status request");
assert.ok(!desktopPolling.includes("refreshWakeStatus"), "polling must not issue a separate wake status request");
for (const removedTimer of ["sessionPollTimer", "residentVoicePollTimer", "wakePollTimer"]) {
  assert.ok(!desktopPolling.includes(removedTimer), `desktop polling helper must not retain independent ${removedTimer} loops`);
}
for (const functionName of ["startAllPolling", "stopAllPolling"]) {
  assert.ok(desktopPolling.includes(functionName), `desktop polling helper must expose ${functionName}`);
}
assert.ok(main.includes('import { createDesktopPolling } from "./components/desktop-polling.js"'), "desktop main must import polling helper");
assert.ok(main.includes("createDesktopPolling({"), "desktop main must create polling helper with refresh callbacks");
assert.ok(main.includes("startAllPolling()"), "desktop main must start polling through helper");
assert.ok(main.includes("stopAllPolling()"), "desktop main must stop polling through helper");
for (const timerName of ["wakePollTimer", "sessionPollTimer", "residentVoicePollTimer"]) {
  assert.ok(!main.includes(timerName), `desktop main must not own ${timerName}`);
}
assert.ok(main.includes("async function completeBackendStart(startPayload)"), "desktop main must define shared backend-start postlude helper");
assert.equal(
  [...main.matchAll(/await completeBackendStart\(startPayload\)/g)].length,
  2,
  "startDesktop and restartBackendForSettings must share backend-start postlude helper",
);
assert.ok(
  main.indexOf("async function completeBackendStart") < main.indexOf("async function startDesktop"),
  "backend-start postlude helper must be shared before startup functions use it",
);
assert.ok(apiClient.includes("parseBackendStartupError"), "api client must normalize backend startup errors");
assert.ok(apiClient.includes("wrapped.diagnostics"), "api client must attach startup diagnostics to thrown errors");
assert.ok(lib.includes("startup_failure_payload"), "Tauri start_backend failures must return structured diagnostics");
assert.ok(backend.includes("stdout_tail"), "backend diagnostics failure payload must include stdout tail");
assert.ok(backend.includes("stderr_tail"), "backend diagnostics failure payload must include stderr tail");
for (const token of ["python_path", "backend_script_path", "working_directory", "endpoint", "stdout_log", "stderr_log", "stdout_tail", "stderr_tail"]) {
  assert.ok(backendDiagnostics.includes(token), `backend diagnostics renderer must include ${token}`);
}
assert.ok(main.includes("await refreshSessionStatus()"), "desktop text and voice flows must refresh session status");
assert.ok(conversationDebug.includes("latest_turn"), "conversation debug must render latest-turn session status");
assert.ok(conversationDebug.includes("artifact_path"), "conversation debug must render turn artifact path");
assert.ok(conversationDebug.includes("runtime_context"), "conversation debug must render runtime context");
assert.ok(conversationDebug.includes("phase_durations_ms"), "conversation debug must render latest-turn phase timing");
assert.ok(conversationDebug.includes("failure_phase"), "conversation debug must render failure phase");
assert.ok(conversationDebug.includes("raw_audio_path"), "conversation debug must render raw audio replay path");
assert.ok(conversationDebug.includes("degraded_reason"), "conversation debug must render compact degraded reason");
assert.ok(!conversationDebug.includes("last_transcript"), "conversation debug must not duplicate transcript text");
assert.ok(!conversationDebug.includes("last_response"), "conversation debug must not duplicate assistant response text");
assert.ok(
  residentVoice.includes("latestTurn?.input_modality === \"voice\""),
  "resident voice completion de-dupe must not key stale voice fields from latest text turns",
);
assert.ok(main.includes("renderDegradedList(readiness, degradedEl)"), "desktop degraded detail must render from existing readiness payload");
assert.ok(
  main.indexOf("await ensureResidentVoiceStream()") < main.indexOf("const readiness = await api.getReadiness()"),
  "desktop must fetch readiness after resident stream startup settles",
);
assert.ok(
  main.indexOf("async function completeBackendStart") < main.indexOf("const readiness = await api.getReadiness()"),
  "desktop backend-start postlude must own readiness fetch",
);
assert.ok(
  main.indexOf("await startWakeMonitorIfAvailable()") > main.indexOf("async function setResidentVoiceMode"),
  "desktop must start wake only through explicit resident mode selection",
);
assert.ok(
  !main
    .slice(main.indexOf("async function completeBackendStart"), main.indexOf("const readiness = await api.getReadiness()"))
    .includes("await startWakeMonitorIfAvailable()"),
  "desktop backend startup must not automatically start wake monitoring",
);
assert.ok(degradedList.includes("closest(\"details\")"), "degraded detail renderer must control its collapsed details container");
assert.ok(degradedList.includes("optional-service"), "degraded detail must label optional services separately");
assert.ok(desktopSource.includes("barge-in"), "desktop must render resident barge-in status");
assert.ok(desktopSource.includes("barge-in-wired"), "desktop must render resident barge-in wiring status");
assert.ok(desktopSource.includes("follow-up-listening"), "desktop must render resident follow-up listening status");
assert.ok(desktopSource.includes("continuous-active"), "desktop must render resident continuous active status");
assert.ok(residentVoice.includes("latestTurnIsVoice && latestTurn?.turn_id"), "resident voice completion dedupe must prefer voice latest-turn identity");
assert.ok(conversationDebug.includes("currentFailureWithoutTurn"), "conversation debug must show current capture failures ahead of stale latest-turn data");
assert.ok(main.includes("ensureResidentVoiceStream"), "desktop must start resident stream before resident wake/mode proof");
assert.ok(main.includes("setResidentVoiceMode"), "desktop must call backend resident mode mutation");
assert.ok(main.includes("setResidentTtsVoice"), "desktop must call backend resident TTS voice mutation");
assert.ok(main.includes("renderResidentTtsVoiceSelector"), "desktop must render TTS voice options from backend status");
assert.ok(main.includes("tts_supported_voices"), "desktop voice selector must use backend-supported voice options");
assert.ok(main.includes("jarvisv7_active_tts_voice"), "desktop voice selector must persist the selected voice locally");
assert.ok(main.includes("applyStoredTtsVoiceIfAvailable"), "desktop voice selector must restore a valid cached voice");
assert.ok(main.includes("removeItem(TTS_VOICE_STORAGE_KEY"), "desktop voice selector must clear invalid cached voices");
const settingsRestartPath = main.slice(main.indexOf("async function restartBackendForSettings"), main.indexOf("function updateSettingsRestartRequired"));
assert.ok(settingsRestartPath.includes("ttsVoicePreferenceRestored = false"), "desktop settings restart must reset TTS voice restore guard");
assert.ok(
  settingsRestartPath.indexOf("ttsVoicePreferenceRestored = false") < settingsRestartPath.indexOf("await completeBackendStart(startPayload)"),
  "desktop settings restart must reset TTS voice guard before backend-start postlude",
);
assert.ok(index.includes("Selected voice is saved locally and applies to runtime."), "desktop voice hint must describe local runtime persistence");
assert.ok(!main.includes("af_bella"), "desktop must not hardcode TTS voice options");
assert.ok(desktopSource.includes("status.stream"), "desktop must read backend resident stream object");
assert.ok(desktopSource.includes("stream_present"), "desktop must keep flat resident stream fallback fields");
assert.ok(desktopSource.includes("degraded_reasons"), "desktop must render resident degraded reasons");
assert.ok(backend.includes("/personality/list"), "backend bridge must call /personality/list");
assert.ok(backend.includes("/personality/select"), "backend bridge must call /personality/select");
assert.ok(lib.includes("get_personality_list"), "Tauri command must expose get_personality_list");
assert.ok(lib.includes("select_personality"), "Tauri command must expose select_personality");
assert.ok(apiClient.includes('invoke("get_personality_list")'), "desktop API client must invoke get_personality_list");
assert.ok(apiClient.includes('invoke("select_personality"'), "desktop API client must invoke select_personality");
assert.ok(index.includes("personality-select"), "desktop must display personality selector");
assert.ok(index.includes("personality-current"), "desktop must display active personality");
assert.ok(main.includes("profile_errors"), "desktop must render backend personality profile diagnostics");
assert.ok(main.includes("Profile diagnostics"), "desktop must label skipped personality profile diagnostics");
assert.ok(main.includes("personalitySelectionPending"), "desktop must guard sends while profile selection is pending");
assert.ok(main.includes("Active personality confirmed"), "desktop must show backend-confirmed active personality");
assert.ok(main.includes("active_personality_profile_id"), "desktop must render backend-reported turn profile metadata");
assert.ok(main.includes("jarvisv7_active_personality"), "desktop must persist the backend-confirmed active personality");
assert.ok(main.includes("dataset.profileId"), "desktop must attach turn profile metadata without appending it to assistant text");
assert.ok(!main.includes("[profile:"), "desktop must not append profile metadata into assistant message text");
assert.ok(main.includes("Description"), "desktop must display profile description");
assert.ok(main.includes("Locale"), "desktop must display profile locale");
assert.ok(main.includes("Default words"), "desktop must display profile default word count");
assert.ok(!main.includes("profile.tone"), "desktop must not depend on old personality tone field");
assert.ok(!main.includes("profile.brevity"), "desktop must not depend on old personality brevity field");
assert.ok(!main.includes("profile.formality"), "desktop must not depend on old personality formality field");
assert.ok(main.includes("appendPresence"), "desktop must append UI-only presence messages");
assert.ok(main.includes("presenceByProfile"), "desktop must map profile-specific presence messages");
assert.ok(settingsPanel.includes("field.options"), "settings panel must render select controls from backend metadata");
assert.ok(settingsPanel.includes("field.section"), "settings panel must group settings from backend metadata");
assert.ok(settingsPanel.includes("field.advanced"), "settings panel must use advanced metadata from backend");
assert.ok(!settingsPanel.includes("LLM_MODEL_MODE"), "settings panel must not hardcode model mode field");
assert.ok(!settingsPanel.includes("Local LLM intent (llama.cpp)"), "settings panel must not hardcode backend sections");
assert.ok(!settingsPanel.includes("http://127.0.0.1:8765/config/operator"), "settings panel must not call backend URL directly");

// Slice Z.4: Desktop State Smoothing assertions
assert.ok(index.includes("System State"), "desktop must display System State label");
assert.ok(index.includes("turn-status-anchor"), "desktop must include turn status anchor container");
assert.ok(index.includes("system-state-card"), "desktop must size System State to Operator column");
assert.ok(main.includes("createDesktopState"), "desktop must create desktop state coordinator");
assert.ok(main.includes("desktopState.renderSystemState"), "desktop must render system state from readiness");
assert.ok(
  main.includes("selectedFamilyBlockers(readiness)"),
  "desktop System State must consider selected required-family readiness",
);
assert.ok(main.includes("desktopState.renderTurnStatus"), "desktop must render turn status from session");
assert.ok(!index.includes("id=\"turn-state\""), "desktop must not keep separate turn-state badge in Conversation header");
const readinessPanelContent = readFileSync(new URL("../src/components/readiness-panel.js", import.meta.url), "utf8");
assert.ok(!readinessPanelContent.includes('["Status"'), "desktop must not include Status fact in readiness summary");
assert.ok(readinessPanelContent.includes('["Arch"'), "desktop must include Arch fact in readiness summary");
assert.ok(readinessPanelContent.includes('["Profile"'), "desktop must include Profile fact in readiness summary");
assert.ok(readinessPanelContent.includes('["LLM"'), "desktop must include LLM fact in readiness summary");

function createElement(tagName) {
  const element = {
    tagName,
    className: "",
    id: "",
    dataset: {},
    textContent: "",
    children: [],
    parentElement: null,
    appendChild(child) {
      child.parentElement = this;
      this.children.push(child);
      return child;
    },
    append(...children) {
      for (const child of children) this.appendChild(child);
    },
    querySelector(selector) {
      if (selector === "#startup-state") return findElement(this, (node) => node.id === "startup-state");
      if (selector === ".label") return findElement(this, (node) => String(node.className).split(" ").includes("label"));
      if (selector === "strong") return findElement(this, (node) => node.tagName === "strong");
      return null;
    },
    querySelectorAll(selector) {
      if (selector === ".turn-status-label") {
        return findElements(this, (node) => String(node.className).split(" ").includes("turn-status-label"));
      }
      return [];
    },
  };
  element.classList = {
    toggle(className, enabled) {
      const classes = new Set(String(element.className).split(" ").filter(Boolean));
      if (enabled) classes.add(className);
      else classes.delete(className);
      element.className = [...classes].join(" ");
    },
  };
  return element;
}

function findElement(node, predicate) {
  if (predicate(node)) return node;
  for (const child of node.children || []) {
    const found = findElement(child, predicate);
    if (found) return found;
  }
  return null;
}

function findElements(node, predicate, found = []) {
  if (predicate(node)) found.push(node);
  for (const child of node.children || []) findElements(child, predicate, found);
  return found;
}

const previousDocument = globalThis.document;
globalThis.document = { createElement };
const shellEl = createElement("main");
const systemCard = createElement("div");
const systemLabel = createElement("span");
systemLabel.className = "label";
const systemValue = createElement("strong");
systemValue.id = "startup-state";
systemCard.append(systemLabel, systemValue);
shellEl.appendChild(systemCard);
const turnAnchor = createElement("div");
const desktopState = createDesktopState(shellEl, turnAnchor);
desktopState.renderTurnStatus("TRANSCRIBING");
desktopState.renderSystemState("BACKEND_UNAVAILABLE");
const railLabels = findElements(turnAnchor, (node) => String(node.className).split(" ").includes("turn-status-label"));
assert.deepEqual(
  railLabels.map((node) => node.textContent),
  ["IDLE", "LISTEN", "TRANSCRIBE", "REASON", "ACT", "RESPOND", "SPEAK", "INTERRUPT", "RECOVER", "FAILED"],
  "Turn Status rail must render compact text labels",
);
assert.equal(
  railLabels.find((node) => node.dataset.label === "TRANSCRIBE").className.includes("active"),
  true,
  "Turn Status must activate the mapped backend state label",
);
assert.equal(systemValue.textContent, "Backend unavailable", "System State must represent backend unavailable");
globalThis.document = previousDocument;

const readyConditions = collectDegradedConditions({
  status: "ready",
  active_llm_runtime: "llama.cpp",
  families: {
    llm: { family: "llm", ready: true, reason: "local llama.cpp available" },
    stt: { family: "stt", ready: true, reason: "stt ready" },
  },
  preflight: { probe_error_count: 0 },
  services: {
    redis: { reachable: true, reason: "reachable" },
    searxng: { reachable: true, reason: "container reachable; json usable" },
  },
  resident_audio: { degraded_reasons: [] },
});
assert.equal(readyConditions.length, 0, "ready desktop payload must not show degraded detail rows");

const degradedConditions = collectDegradedConditions({
  status: "degraded",
  active_llm_runtime: "ollama",
  families: {
    llm: { family: "llm", ready: true, reason: "test ollama available", degraded_reason: "Degraded-no-sidecar-binary" },
    stt: { family: "stt", ready: false, reason: "STT model missing" },
    tts: { family: "tts", ready: true, reason: "tts ready" },
  },
  preflight: { probe_error_count: 1 },
  services: {
    redis: { reachable: false, reason: "connection refused" },
  },
  resident_audio: { degraded_reasons: ["resident audio stream is stopped"] },
});
assert.deepEqual(
  degradedConditions.map((row) => row.kind),
  ["backend", "family", "resident-audio", "optional-service"],
  "degraded detail must include selected-path blockers, resident audio reasons, and optional services separately",
);

const selectedFamilyOnlyConditions = collectDegradedConditions({
  status: "ready",
  active_llm_runtime: "llama.cpp",
  families: {
    llm: { family: "llm", ready: false, reason: "selected llama.cpp path unavailable" },
    stt: { family: "stt", ready: true, reason: "stt ready" },
  },
  preflight: { probe_error_count: 0 },
  services: {
    redis: { reachable: false, reason: "connection refused" },
  },
  resident_audio: { degraded_reasons: [] },
});
assert.deepEqual(
  selectedFamilyBlockers({
    status: "ready",
    active_llm_runtime: "llama.cpp",
    families: {
      llm: { family: "llm", ready: false, reason: "selected llama.cpp path unavailable" },
      stt: { family: "stt", ready: true, reason: "stt ready" },
    },
    services: {
      redis: { reachable: false, reason: "connection refused" },
    },
  }).map((family) => family.family),
  ["llm"],
  "System State degradation must use selected required-family blockers and ignore optional services",
);
assert.deepEqual(
  selectedFamilyOnlyConditions.map((row) => row.kind),
  ["family", "optional-service"],
  "selected-family blockers and optional service detail rows must remain distinct",
);

const backendDiagnosticsEl = { textContent: "" };
renderBackendDiagnostics(
  {
    failure: "backend startup failed",
    diagnostics: {
      python_path: "repo\\backend\\.venv\\Scripts\\python.exe",
      backend_script_path: "repo\\scripts\\run_backend.py",
      working_directory: "repo",
      host: "127.0.0.1",
      port: 8765,
      stdout_log: "repo\\reports\\backend_startup.log",
      stderr_log: "repo\\reports\\backend_spawn_stderr.log",
    },
    stdout_tail: "stdout line",
    stderr_tail: "stderr line",
  },
  backendDiagnosticsEl,
);
for (const expected of [
  "failure: backend startup failed",
  "python_path: repo\\backend\\.venv\\Scripts\\python.exe",
  "backend_script_path: repo\\scripts\\run_backend.py",
  "working_directory: repo",
  "endpoint: 127.0.0.1:8765",
  "stdout_log: repo\\reports\\backend_startup.log",
  "stderr_log: repo\\reports\\backend_spawn_stderr.log",
  "stdout_tail:\nstdout line",
  "stderr_tail:\nstderr line",
]) {
  assert.ok(backendDiagnosticsEl.textContent.includes(expected), `backend diagnostics output must include ${expected}`);
}

const readyLlamaCppConditions = collectDegradedConditions({
  status: "ready",
  active_llm_runtime: "llama.cpp",
  families: {
    llm: {
      family: "llm",
      ready: true,
      reason: "local llama.cpp available",
      degraded_reason: "llama.cpp /v1/models reachable",
    },
  },
  preflight: { probe_error_count: 0 },
  services: {},
  resident_audio: { degraded_reasons: [] },
});
assert.equal(
  readyLlamaCppConditions.some((row) => row.title === "LLM selected path degraded"),
  false,
  "ready llama.cpp must not show an LLM degraded detail solely because degraded_reason exists",
);

const staleVoiceDetail = { textContent: "" };
renderConversationDebug(
  {
    state: "IDLE",
    invocation_source: "wake",
    failure_reason: "stale voice failure",
    tts_output_device: "stale output device",
    latest_turn: {
      turn_id: "text-turn-123",
      input_modality: "text",
      final_state: "IDLE",
      failure_reason: null,
      tts_output_device: null,
      artifact_path: "data\\turns\\session\\text-turn-123.json",
      runtime_context: { llm: "llama.cpp" },
    },
  },
  staleVoiceDetail,
);
assert.ok(staleVoiceDetail.textContent.includes("turn: text text-t IDLE"), "text latest turn must render text source");
assert.ok(staleVoiceDetail.textContent.includes("runtime: llm=llama.cpp"), "text latest turn must render latest runtime context");
assert.ok(!staleVoiceDetail.textContent.includes("wake"), "text latest turn must not show stale voice source");
assert.ok(!staleVoiceDetail.textContent.includes("stale voice failure"), "text latest turn must not show stale flat failure");
assert.ok(!staleVoiceDetail.textContent.includes("stale output device"), "text latest turn must not show stale flat TTS output");

const appendedMessages = [];
const residentPresenter = createResidentVoicePresenter({
  pttButton: {
    dataset: {},
    disabled: false,
    textContent: "",
    setAttribute(name, value) {
      this[name] = value;
    },
  },
  voiceStatusEl: { textContent: "" },
  residentModeEl: null,
  residentStatusEl: null,
  setState() {},
  showError() {},
  appendMessage(role, text) {
    appendedMessages.push({ role, text });
  },
});
residentPresenter.renderResidentVoiceStatus({
  state: "IDLE",
  invocation_source: "wake",
  last_transcript: "Hey Jarvis, what is the capital of the United States?",
  last_response: "The capital of the United States is Washington, D.C.",
  latest_turn: {
    turn_id: "text-turn-123",
    input_modality: "text",
    final_state: "IDLE",
    failure_reason: null,
  },
});
assert.deepEqual(
  appendedMessages,
  [],
  "resident voice presenter must not append stale wake completion after latest text turn",
);
residentPresenter.renderResidentVoiceStatus({
  state: "IDLE",
  invocation_source: "wake",
  last_transcript: "Hey Jarvis, what is the capital of the United States?",
  last_response: "The capital of the United States is Washington, D.C.",
  latest_turn: {
    turn_id: "voice-turn-123",
    input_modality: "voice",
    final_state: "IDLE",
    failure_reason: null,
  },
});
assert.deepEqual(
  appendedMessages.map((message) => message.role),
  ["user", "assistant"],
  "resident voice presenter must still append current voice completions",
);

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function memoryRecord(overrides = {}) {
  return {
    fact_id: "memory-1",
    revision: 1,
    text: "The user prefers concise answers.",
    value: "concise",
    lifecycle_state: "pending_review",
    ...overrides,
  };
}

function memoryDetail(record = memoryRecord()) {
  return {
    record,
    evidence: [],
    events: [],
    evidence_total: 0,
    evidence_returned: 0,
    events_total: 0,
    events_returned: 0,
  };
}

const firstList = deferred();
const listController = createMemoryPanelController({
  listMemories: ({ query }) =>
    query === "old"
      ? firstList.promise
      : Promise.resolve({ records: [memoryRecord({ fact_id: "new", text: "new result" })] }),
});
const staleListRequest = listController.refreshList({ query: "old" });
await listController.refreshList({ query: "new" });
firstList.resolve({ records: [memoryRecord({ fact_id: "old", text: "old result" })] });
await staleListRequest;
assert.equal(listController.snapshot().list.records[0].fact_id, "new", "stale list responses must not replace newer filters");

const firstDetail = deferred();
const detailController = createMemoryPanelController({
  getMemoryDetail: (factId) =>
    factId === "old" ? firstDetail.promise : Promise.resolve(memoryDetail(memoryRecord({ fact_id: "new" }))),
});
const staleDetailRequest = detailController.selectMemory("old");
await detailController.selectMemory("new");
firstDetail.resolve(memoryDetail(memoryRecord({ fact_id: "old" })));
await staleDetailRequest;
assert.equal(detailController.snapshot().detail.record.fact_id, "new", "stale detail responses must not replace newer selection");

const failedMutation = deferred();
const mutationSnapshots = [];
const mutationController = createMemoryPanelController(
  {
    getMemoryDetail: () => Promise.resolve(memoryDetail()),
    listMemories: () => Promise.resolve({ records: [memoryRecord()] }),
    confirmMemory: () => failedMutation.promise,
  },
  (snapshot) => mutationSnapshots.push(snapshot),
);
await mutationController.selectMemory("memory-1");
const pendingConfirm = mutationController.confirm();
assert.equal(mutationController.snapshot().mutationPending, true, "mutation lock must engage while request is pending");
assert.equal(mutationController.snapshot().detail.record.text, "The user prefers concise answers.", "pending mutation must retain record");
failedMutation.reject(new Error("confirm failed"));
await pendingConfirm;
assert.equal(mutationController.snapshot().mutationPending, false, "mutation lock must release after failure");
assert.equal(mutationController.snapshot().detail.record.revision, 1, "failed confirm must retain rendered revision");
assert.ok(
  mutationSnapshots.some((snapshot) => snapshot.mutationPending) &&
    mutationSnapshots.at(-1).mutationPending === false,
  "rendered mutation state must disable then re-enable controls",
);

let conflictDetailReads = 0;
const recordConflict = new Error("conflict");
recordConflict.status = 409;
recordConflict.detail = { error: "conflict", current_revision: 2, current_state: "active" };
const conflictController = createMemoryPanelController({
  getMemoryDetail: () =>
    Promise.resolve(memoryDetail(memoryRecord({ revision: ++conflictDetailReads, lifecycle_state: conflictDetailReads > 1 ? "active" : "pending_review" }))),
  listMemories: () => Promise.resolve({ records: [memoryRecord({ revision: 2, lifecycle_state: "active" })] }),
  confirmMemory: () => Promise.reject(recordConflict),
});
await conflictController.selectMemory("memory-1");
await conflictController.confirm();
assert.equal(conflictController.snapshot().detail.record.revision, 2, "record 409 must reload current backend detail");
assert.ok(conflictController.snapshot().conflict.includes("not applied"), "record 409 must remain visibly actionable");

let policyReads = 0;
const policyConflict = new Error("policy conflict");
policyConflict.status = 409;
policyConflict.detail = { error: "conflict", current_revision: 2, current_state: "enabled" };
const policyController = createMemoryPanelController({
  getMemoryPolicy: () =>
    Promise.resolve({ automatic_curation_enabled: policyReads++ > 0, revision: policyReads, updated_at: "now" }),
  updateMemoryPolicy: () => Promise.reject(policyConflict),
  getMemoryCurationStatus: () => Promise.resolve({}),
});
await policyController.refreshPolicy();
await policyController.updatePolicy(true);
assert.equal(policyController.snapshot().policy.revision, 2, "policy 409 must reload current backend policy");
assert.ok(policyController.snapshot().conflict.includes("reloaded"), "policy 409 must display visible reload conflict");

let forgetCalls = 0;
const forgetResponse = deferred();
const forgetController = createMemoryPanelController({
  getMemoryDetail: () => Promise.resolve(memoryDetail()),
  listMemories: () => Promise.resolve({ records: [memoryRecord()] }),
  forgetMemory: () => {
    forgetCalls += 1;
    return forgetResponse.promise;
  },
});
await forgetController.selectMemory("memory-1");
await forgetController.forget(() => Promise.resolve(false));
assert.equal(forgetCalls, 0, "forget must require explicit confirmation");
const pendingForget = forgetController.forget(() => Promise.resolve(true));
await Promise.resolve();
assert.equal(forgetCalls, 1, "confirmed forget must call the backend once");
assert.equal(forgetController.snapshot().detail.record.lifecycle_state, "pending_review", "forget must not optimistically remove or alter the record");
forgetResponse.resolve(memoryDetail(memoryRecord({ revision: 2, lifecycle_state: "forgotten" })));
await pendingForget;

for (const action of ["correct", "dispute", "forget"]) {
  const controller = createMemoryPanelController({
    getMemoryDetail: () => Promise.resolve(memoryDetail()),
    listMemories: () => Promise.resolve({ records: [memoryRecord()] }),
    [`${action}Memory`]: () => Promise.reject(new Error(`${action} failed`)),
  });
  await controller.selectMemory("memory-1");
  if (action === "correct") {
    await controller.correct({ replacementText: "replacement" });
  } else if (action === "forget") {
    await controller.forget(() => Promise.resolve(true));
  } else {
    await controller.dispute();
  }
  assert.equal(controller.snapshot().detail.record.revision, 1, `failed ${action} must retain the rendered record`);
}

let correctionDetailId = "memory-1";
const correctionController = createMemoryPanelController({
  getMemoryDetail: (factId) => {
    correctionDetailId = factId;
    return Promise.resolve(memoryDetail(memoryRecord({ fact_id: factId, revision: factId === "memory-2" ? 1 : 2 })));
  },
  listMemories: () => Promise.resolve({ records: [] }),
  correctMemory: () =>
    Promise.resolve({
      original: memoryRecord({ revision: 2, superseded_by_fact_id: "memory-2", lifecycle_state: "superseded" }),
      replacement: memoryRecord({ fact_id: "memory-2", text: "The user prefers detailed answers.", value: "detailed" }),
      relation: "superseded_by",
    }),
});
await correctionController.selectMemory("memory-1");
await correctionController.correct({ replacementText: "The user prefers detailed answers.", replacementValue: "detailed" });
assert.equal(correctionDetailId, "memory-2", "successful correction must refresh replacement detail from backend");
assert.equal(correctionController.snapshot().correction.original.superseded_by_fact_id, "memory-2", "correction must retain original supersession truth");
assert.equal(correctionController.snapshot().correction.replacement.fact_id, "memory-2", "correction must retain replacement truth");

assert.equal(
  memoryActionsEnabled(memoryRecord({ lifecycle_state: "superseded" }), false),
  true,
  "renderer must not disable actions from lifecycle transition policy",
);
assert.equal(
  memoryActionsEnabled(memoryRecord({ lifecycle_state: "backend_future_state" }), true),
  false,
  "the in-flight mutation lock must remain the only renderer action gate",
);

let submittedRevision = null;
const invalidTransition = new Error("invalid transition");
invalidTransition.detail = {
  error: "invalid_transition",
  message: "confirm memory transition is not allowed",
};
const backendOwnedTransitionController = createMemoryPanelController({
  getMemoryDetail: () =>
    Promise.resolve(memoryDetail(memoryRecord({ revision: 7, lifecycle_state: "superseded" }))),
  confirmMemory: (_factId, expectedRevision) => {
    submittedRevision = expectedRevision;
    return Promise.reject(invalidTransition);
  },
});
await backendOwnedTransitionController.selectMemory("memory-1");
await backendOwnedTransitionController.confirm();
assert.equal(submittedRevision, 7, "renderer must submit the current revision and let the backend decide transition validity");
assert.equal(
  backendOwnedTransitionController.snapshot().detail.record.lifecycle_state,
  "superseded",
  "backend transition rejection must retain the inspected record",
);
assert.equal(
  backendOwnedTransitionController.snapshot().detailError,
  "confirm memory transition is not allowed",
  "backend transition rejection must display typed backend truth",
);

const availableIdleCuration = {
  service_available: true,
  processor_available: true,
  worker_running: true,
  drain_active: false,
  degraded: false,
  retry_blocked: false,
  pending_count: 0,
  processing_count: 0,
  failed_count: 0,
  current_job_id: null,
};
assert.equal(
  curationActivityState(availableIdleCuration),
  "idle",
  "an available worker without active work must display idle",
);
assert.equal(
  curationActivityState({ ...availableIdleCuration, processing_count: 1 }),
  "running",
  "a processing job must display running",
);
assert.equal(
  curationActivityState({ ...availableIdleCuration, current_job_id: "job-1" }),
  "running",
  "a current job must display running",
);
assert.equal(
  curationActivityState({ ...availableIdleCuration, drain_active: true }),
  "running",
  "an active drain must display running",
);
assert.equal(
  curationActivityState({ ...availableIdleCuration, degraded: true }),
  "degraded",
  "backend degraded status must remain degraded",
);
assert.equal(
  curationActivityState({ ...availableIdleCuration, retry_blocked: true }),
  "blocked",
  "backend blocked status must remain blocked",
);

const panelEvents = [];
let memoryOpen = false;
let settingsOpen = true;
const coordinator = createOperatorPanelCoordinator({
  isMemoryOpen: () => memoryOpen,
  openMemory: async () => {
    panelEvents.push("open-memory");
    memoryOpen = true;
  },
  closeMemory: () => {
    panelEvents.push("close-memory");
    memoryOpen = false;
  },
  focusMemoryTrigger: () => panelEvents.push("focus-memory"),
  isSettingsOpen: () => settingsOpen,
  openSettings: async () => {
    panelEvents.push("open-settings");
    settingsOpen = true;
  },
  closeSettings: () => {
    panelEvents.push("close-settings");
    settingsOpen = false;
  },
  focusSettingsTrigger: () => panelEvents.push("focus-settings"),
});
await coordinator.toggleMemory();
assert.deepEqual(panelEvents, ["close-settings", "open-memory"], "memory open must deterministically close settings first");
panelEvents.length = 0;
await coordinator.toggleSettings();
assert.deepEqual(panelEvents, ["close-memory", "open-settings"], "settings open must deterministically close memory first");

for (const command of [
  "get_memory_policy",
  "update_memory_policy",
  "list_memories",
  "get_memory_detail",
  "confirm_memory",
  "correct_memory",
  "dispute_memory",
  "forget_memory",
  "get_memory_curation_status",
]) {
  assert.ok(apiClient.includes(`invokeMemory(invoke, "${command}"`), `API client must use Tauri command ${command}`);
  assert.ok(lib.includes(command), `Tauri handler must register ${command}`);
}
for (const route of ["/memory/policy", "/memory/curation/status", "/memory/{fact_id}"]) {
  assert.ok(backend.includes(route), `backend bridge must include ${route}`);
}
for (const field of [
  "evidence_authority",
  "lifecycle_state",
  "eligible_for_normal_retrieval",
  "expectedRevision",
  "source_session_id",
  "source_turn_id",
  "source_field",
  "superseded_by_fact_id",
]) {
  assert.ok(memoryPanel.includes(field) || apiClient.includes(field), `memory surface must include ${field}`);
}
assert.ok(!memoryPanel.includes("innerHTML"), "memory panel must render backend text without innerHTML");
assert.ok(!memoryPanel.includes("fetch("), "memory panel must not call backend HTTP directly");
assert.ok(!memoryPanel.includes("localStorage"), "memory policy must not be persisted in renderer storage");
assert.ok(!memoryPanel.includes("ACTION_STATES"), "renderer must not duplicate lifecycle transition policy");
assert.ok(!memoryPanel.includes(".has(record.lifecycle_state)"), "action availability must not be inferred from lifecycle state");
assert.ok(index.includes('id="memory-trigger"'), "operator area must expose one Memory control");
assert.ok(index.includes('id="memory-panel"'), "operator area must include one hidden Memory panel");

console.log("desktop static and memory behavior checks passed");
