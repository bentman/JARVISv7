import { test } from "node:test";
import { strict as assert } from "node:assert";
import { renderConversationDebug } from "../src/components/conversation-debug.js";
import { renderBackendDiagnostics } from "../src/components/backend-diagnostics.js";
import { collectDegradedConditions, selectedFamilyBlockers } from "../src/components/degraded-list.js";
import { createDesktopState } from "../src/components/desktop-state.js";
import { createResidentVoicePresenter } from "../src/components/resident-voice.js";
import { createDesktopPolling, sessionPollingInterval, statusPollingInterval } from "../src/components/desktop-polling.js";
import { createSearchStatus, renderSearchEvidence } from "../src/components/search-evidence.js";
import { createApiClient } from "../src/api-client.js";
import { renderReadiness } from "../src/components/readiness-panel.js";
import { renderWakeStatus } from "../src/components/wake-indicator.js";
import { renderServiceStatus } from "../src/components/service-status.js";
import { createHandoffStatus } from "../src/components/agents-panel.js";
import { main, backend, createElement, findElement, findElements } from "./support.mjs";

test("active sessions must retain responsive polling", async () => {
  assert.equal(sessionPollingInterval({ state: "reasoning" }), 100, "active sessions must retain responsive polling");
  assert.equal(sessionPollingInterval({ state: "IDLE" }), 2000, "idle sessions must reduce polling churn");
  assert.equal(sessionPollingInterval({ state: "reasoning" }, false), 10000, "hidden windows must throttle session polling");
  assert.equal(statusPollingInterval(), 3000, "resident and wake status polling must reduce idle churn");
  assert.equal(statusPollingInterval(false), 10000, "hidden windows must throttle status polling");
});

test("desktop statuses must share one adaptive poll timer", async () => {
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
});

test("provider api calls must use their Tauri commands", async () => {
  const providerInvocations = [];
  const providerApi = createApiClient(async (command, args) => {
    providerInvocations.push({ command, args });
    return JSON.stringify({ ok: true });
  });
  await providerApi.getLlmConfig();
  await providerApi.updateLlmProfile("profile-1", { name: "Lab" });
  await providerApi.updateLlmSelection({ primary_profile_id: "profile-1" });
  assert.deepEqual(providerInvocations, [
    { command: "get_llm_config", args: {} },
    { command: "update_llm_profile", args: { profileId: "profile-1", profile: { name: "Lab" } } },
    { command: "update_llm_selection", args: { selection: { primary_profile_id: "profile-1" } } },
  ]);
});

test("search evidence must render source titles as text and refuse unsafe links", async () => {
  const previousDocument = globalThis.document;
  globalThis.document = { createElement };
  try {
    const searchContainer = createElement("div");
    const openedSources = [];
    renderSearchEvidence(searchContainer, { sources: [
      { id: "S1", title: "<img onerror=evil()>", url: "https://example.com/?v=2", basis: "page_excerpt", retrieved_at: "now" },
      { id: "S2", title: "bad", url: "javascript:evil()" },
    ] }, (url) => openedSources.push(url), assert.fail);
    const sourceLink = searchContainer.children[0].children[0];
    assert.equal(sourceLink.textContent, "[S1] <img onerror=evil()>");
    assert.equal(searchContainer.children[0].children.length, 1);
    let prevented = false;
    sourceLink.listeners.click({ preventDefault() { prevented = true; } });
    assert.ok(prevented);
    assert.deepEqual(openedSources, ["https://example.com/?v=2"]);
    const searchLabel = createElement("span");
    const searchStop = createElement("button");
    const cancelledSearches = [];
    const searchPresenter = createSearchStatus({
      label: searchLabel, stopButton: searchStop,
      cancelSearch: async (...args) => cancelledSearches.push(args), onError: assert.fail,
    });
    searchPresenter.render({ session_id: "s", turn_id: "t", stage: "searching", current_provider: "searxng", attempts: [{ provider: "ddgs", status: "timeout" }] });
    assert.match(searchLabel.textContent, /Searching.*searxng.*ddgs: timeout/);
    await searchStop.listeners.click();
    assert.deepEqual(cancelledSearches, [["s", "t"]]);
    assert.ok(searchStop.disabled);
    searchPresenter.render({ session_id: "s", turn_id: "t", stage: "reading" });
    assert.equal(searchLabel.textContent, "Stopping search…");
    searchPresenter.render(null);
    assert.ok(searchStop.hidden);
    assert.equal(sessionPollingInterval({ state: "IDLE", active_search: { stage: "planning" } }), 100);
    const handoffLabel = createElement("span");
    const handoffEnd = createElement("button");
    const endedHandoffs = [];
    let handoffRefreshes = 0;
    const handoffPresenter = createHandoffStatus({
      label: handoffLabel, endButton: handoffEnd,
      endHandoff: async (sessionId) => endedHandoffs.push(sessionId),
      onEnded: async () => { handoffRefreshes += 1; },
      onError: assert.fail,
    });
    handoffPresenter.render({ session_id: "s", active_agent: { profile_id: "notes", display_name: "Notes" } });
    assert.equal(handoffLabel.textContent, "Talking to Notes", "an active handoff must say which agent owns the conversation");
    assert.equal(handoffEnd.hidden, false);
    await handoffEnd.listeners.click();
    assert.deepEqual(endedHandoffs, ["s"], "ending a handoff must name the session it belongs to");
    assert.equal(handoffRefreshes, 1, "ending a handoff must refresh session status");
    handoffPresenter.render({ session_id: "s", active_agent: null });
    assert.equal(handoffLabel.textContent, "");
    assert.ok(handoffEnd.hidden, "the End control must hide when no agent owns the conversation");
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
  } finally {
    globalThis.document = previousDocument;
  }
});

test("ready desktop payload must not show degraded detail rows", async () => {
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
});

test("degraded detail must include selected-path blockers, resident audio reasons, and optional services separately", async () => {
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
});

test("System State degradation must use selected required-family blockers and ignore optional services", async () => {
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
});

test("backend startup failures must render their launch diagnostics", async () => {
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
});

test("ready llama.cpp must not show an LLM degraded detail solely because degraded_reason exists", async () => {
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
});

test("text latest turn must render text source", async () => {
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
});

test("resident voice presenter must not append stale wake completion after latest text turn", async () => {
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
    appendMessage(role, text, metadata) {
      appendedMessages.push({ role, text, metadata });
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
      search: { sources: [{ id: "S1", url: "https://example.com/" }] },
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
  assert.equal(appendedMessages[1].metadata.search.sources[0].id, "S1");
});

test("the wake indicator must render backend wake state", async () => {
  const previousDocument = globalThis.document;
  globalThis.document = { createElement };
  try {
    // wake-indicator.js tests
    const container = createElement("div");
    renderWakeStatus({
      provider: "test-wake",
      available: true,
      active: true,
      monitoring: true,
      reason: "ok",
      detection_count: 5,
      last_detected: "recently",
      last_score: 0.95,
      threshold: 0.5
    }, container);
    
    assert.equal(container.dataset.available, "true");
    assert.equal(container.dataset.active, "true");
    assert.equal(container.dataset.monitoring, "true");
    
    const summary = findElement(container, (n) => String(n.className).includes("wake-indicator-summary"));
    assert.ok(summary.textContent.includes("test-wake"), "summary must include provider name");
    
    const providerField = findElement(container, (n) => String(n.className).includes("wake-indicator-value") && n.textContent === "test-wake");
    assert.ok(providerField, "provider must render in fields");
    
    const scoreField = findElement(container, (n) => String(n.className).includes("wake-indicator-value") && n.textContent.includes("0.950"));
    assert.ok(scoreField, "score and threshold must render formatted");
  } finally {
    globalThis.document = previousDocument;
  }
});

test("service status must render each optional service's reachability", async () => {
  const previousDocument = globalThis.document;
  globalThis.document = { createElement };
  try {
    // service-status.js tests
    const container = createElement("div");
    renderServiceStatus({
      redis: { reachable: true, endpoint: "localhost:6379" },
      searxng: { reachable: false, reason: "container unavailable" }
    }, container);
    
    const dots = findElements(container, (n) => String(n.className).includes("service-status-dot"));
    assert.equal(dots.length, 2, "must render lines for redis and searxng");
    assert.equal(dots[0].dataset.status, "reachable", "redis should be reachable");
    assert.equal(dots[1].dataset.status, "unavailable", "searxng should be unavailable");
    
    const details = findElements(container, (n) => String(n.className).split(" ").includes("service-status-detail"));
    assert.ok(details[0].textContent.includes("localhost:6379"), "redis endpoint must render");
    assert.ok(details[1].textContent.includes("container unavailable"), "searxng reason must render");
  } finally {
    globalThis.document = previousDocument;
  }
});

test("the readiness panel must render family readiness", async () => {
  const previousDocument = globalThis.document;
  globalThis.document = { createElement };
  try {
    // readiness-panel.js tests
    const container = createElement("div");
    renderReadiness({
      status: "ready",
      arch: "amd64",
      profile_id: "jarvis",
      active_llm_runtime: "llama.cpp",
      families: {
        llm: { family: "llm", ready: true, runtime: "llama", device: "cpu", reason: "ok" },
        stt: { family: "stt", ready: false, runtime: "whisper", device: "gpu", reason: "missing model" }
      }
    }, container);
    
    const labels = findElements(container, (n) => n.tagName === "dt").map(n => n.textContent);
    assert.ok(labels.includes("Arch"), "readiness panel must render Arch fact");
    assert.ok(labels.includes("Profile"), "readiness panel must render Profile fact");
    assert.ok(labels.includes("LLM"), "readiness panel must render LLM fact");
    assert.ok(!labels.includes("Status"), "readiness panel must not render Status fact");
    
    const familyRows = findElements(container, (n) => String(n.className).includes("readiness-family"));
    assert.ok(familyRows.length >= 2, "readiness panel must render family rows");
    
    const sttRow = familyRows.find(n => n.dataset && n.dataset.family === "stt");
    assert.ok(sttRow, "STT family row must be rendered");
    assert.ok(sttRow.title.includes("missing model"), "readiness panel must use family reason as title");
  } finally {
    globalThis.document = previousDocument;
  }
});

test("a failed operation must not leave System State stuck at a failure", async () => {
  const previousDocument = globalThis.document;
  globalThis.document = { createElement };
  try {
    const shellEl = createElement("main");
    const systemCard = createElement("div");
    const systemValue = createElement("strong");
    systemValue.id = "startup-state";
    systemCard.appendChild(systemValue);
    shellEl.appendChild(systemCard);
    const errorPanel = createElement("div");
    errorPanel.className = "hidden";
    const desktopState = createDesktopState(shellEl, createElement("div"), errorPanel);

    desktopState.renderSystemState("READY");
    desktopState.showError("Resident voice invocation failed: timeout");
    assert.equal(errorPanel.textContent, "Resident voice invocation failed: timeout");
    assert.equal(errorPanel.className.includes("hidden"), false, "the operation error must be visible");
    assert.equal(systemValue.textContent, "Ready", "an operation failure must not replace the backend's system state");

    desktopState.clearError();
    assert.equal(errorPanel.className.includes("hidden"), true);
    assert.equal(errorPanel.textContent, "");

    desktopState.showError("backend exited", "BACKEND_UNAVAILABLE");
    assert.equal(systemValue.textContent, "Backend unavailable", "a lifecycle failure must still set System State");
  } finally {
    globalThis.document = previousDocument;
  }
});
