import { existsSync, readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { renderConversationDebug } from "../src/components/conversation-debug.js";
import { renderBackendDiagnostics } from "../src/components/backend-diagnostics.js";
import { collectDegradedConditions, selectedFamilyBlockers } from "../src/components/degraded-list.js";
import { createDesktopState } from "../src/components/desktop-state.js";
import { createResidentVoicePresenter } from "../src/components/resident-voice.js";
import { createDesktopPolling, sessionPollingInterval, statusPollingInterval } from "../src/components/desktop-polling.js";
import { createSearchStatus, renderSearchEvidence } from "../src/components/search-evidence.js";
import { createApiClient } from "../src/api-client.js";
import { restartScopeDisables } from "../src/components/settings-panel.js";
import {
  builtinProfileNotice,
  defaultEditingProfile,
  providerChoiceGroups,
  providerRestartDisabled,
  providerSelectionPayload,
} from "../src/components/llm-provider-settings.js";
import { createAdvancedPanelCoordinator } from "../src/components/advanced-panel.js";
import {
  createMemoryPanelController,
  curationActivityState,
  formatCurationResult,
  memoryActionsEnabled,
} from "../src/components/memory-panel.js";
import {
  actionApprovalEnabled,
  capabilityActivityState,
  capabilityArgumentFields,
  coerceArguments,
  createActionsPanel,
  createActionsPanelController,
  proposeEnabled,
  executionActivityState,
  formatCapabilityApproval,
  formatCapabilityRisk,
} from "../src/components/actions-panel.js";
import {
  createExtensionsPanelController,
  extensionActivityState,
  extensionStateEnabled,
  formatExtensionOrigin,
  requestedCapabilities,
} from "../src/components/extensions-panel.js";
import {
  agentCancelNotice,
  agentInvokeEnabled,
  agentInvokeNotice,
  agentRunActivityState,
  agentRunProfileId,
  createAgentsPanelController,
} from "../src/components/agents-panel.js";

const main = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");
const apiClient = readFileSync(new URL("../src/api-client.js", import.meta.url), "utf8");
const residentVoice = readFileSync(new URL("../src/components/resident-voice.js", import.meta.url), "utf8");
const conversationDebug = readFileSync(new URL("../src/components/conversation-debug.js", import.meta.url), "utf8");
const backendDiagnostics = readFileSync(new URL("../src/components/backend-diagnostics.js", import.meta.url), "utf8");
const desktopPolling = readFileSync(new URL("../src/components/desktop-polling.js", import.meta.url), "utf8");
const degradedList = readFileSync(new URL("../src/components/degraded-list.js", import.meta.url), "utf8");
const settingsPanel = readFileSync(new URL("../src/components/settings-panel.js", import.meta.url), "utf8");
const llmProviderSettings = readFileSync(new URL("../src/components/llm-provider-settings.js", import.meta.url), "utf8");
const memoryPanel = readFileSync(new URL("../src/components/memory-panel.js", import.meta.url), "utf8");
const actionsPanel = readFileSync(new URL("../src/components/actions-panel.js", import.meta.url), "utf8");
const extensionsPanel = readFileSync(new URL("../src/components/extensions-panel.js", import.meta.url), "utf8");
const agentsPanel = readFileSync(new URL("../src/components/agents-panel.js", import.meta.url), "utf8");
const backend = readFileSync(new URL("../src-tauri/src/backend.rs", import.meta.url), "utf8");
const lib = readFileSync(new URL("../src-tauri/src/lib.rs", import.meta.url), "utf8");
const index = readFileSync(new URL("../src/index.html", import.meta.url), "utf8");
const style = readFileSync(new URL("../src/style.css", import.meta.url), "utf8");
const cargoToml = readFileSync(new URL("../src-tauri/Cargo.toml", import.meta.url), "utf8");
const tauriConfig = JSON.parse(readFileSync(new URL("../src-tauri/tauri.conf.json", import.meta.url), "utf8"));
const desktopSource = main + apiClient + residentVoice;

const extensionCalls = [];
const extensionController = createExtensionsPanelController({
  invokeExtension: async (...args) => { extensionCalls.push(["invoke", ...args]); return { status: "awaiting_approval" }; },
  answerExtensionInput: async (...args) => { extensionCalls.push(["answer", ...args]); },
  decideAction: async (...args) => { extensionCalls.push(["decide", ...args]); },
  cancelAction: async (...args) => { extensionCalls.push(["cancel", ...args]); },
  getExtensionRuns: async () => ({ runs: [] }),
}, () => undefined);
await extensionController.invoke("acp:agent", "capability", { prompt: "hello" });
await extensionController.answer("run", "request", { action: "accept", content: { value: "ok" } });
await extensionController.decide("proposal", "approved");
await extensionController.decide("proposal", "denied");
assert.deepEqual(extensionCalls, [
  ["invoke", "acp:agent", "capability", { prompt: "hello" }],
  ["answer", "run", "request", { action: "accept", content: { value: "ok" } }],
  ["decide", "proposal", "approved"],
  ["decide", "proposal", "denied"],
]);
const failingExtensionController = createExtensionsPanelController({
  invokeExtension: async () => { throw new Error("blocked"); },
}, () => undefined);
await failingExtensionController.invoke("mcp:server", "capability", {});
assert.equal(failingExtensionController.snapshot().detailError, "blocked");
assert.ok(extensionsPanel.includes("data-draft-key"), "extension forms must retain drafts across run refreshes");

const agentProfile = {
  profile_id: "researcher",
  display_name: "Researcher",
  purpose: "Investigate a question",
  invocation_modes: ["direct", "as_tool"],
  capability_ids: ["search-public-web"],
  memory_scope: "episodic",
  approval_class: "standard",
  cancellable: true,
};
const agentRunRecord = {
  kind: "action_proposal",
  capability_id: "agent-invoke-researcher",
  proposal_id: "p-1",
  recorded_at: "2026-09-07T10:00:00+00:00",
  record: { proposal_id: "p-1", status: "awaiting_approval" },
};
assert.equal(agentRunProfileId(agentRunRecord), "researcher", "agent runs must derive the profile from the capability id");
assert.equal(agentRunProfileId({ capability_id: "extension-invoke-x" }), "", "non-agent audit records must not claim an agent");
assert.equal(agentRunActivityState(agentRunRecord), "blocked", "an unapproved agent run must not read as active");
assert.equal(agentRunActivityState({ record: { status: "success" } }), "succeeded");
assert.equal(agentRunActivityState({}), "idle", "an audit record without a nested status must not invent one");
assert.equal(agentInvokeNotice({ status: "awaiting_approval" }), "Agent invocation is awaiting approval.", "governed invocations must not report success");
assert.equal(agentInvokeNotice({ status: "success" }), "Agent run completed.");
assert.equal(agentCancelNotice({ profile_id: "researcher", cancelled: false }), "No cancellable agent run was found.", "a refused cancel must be reported honestly");
assert.equal(agentCancelNotice({ profile_id: "researcher", cancelled: true }), "Agent run cancelled.");
assert.equal(agentInvokeEnabled(agentProfile, " ", false), false, "an empty prompt must not invoke an agent");
assert.equal(agentInvokeEnabled({ ...agentProfile, invocation_modes: ["as_tool"] }, "go", false), false, "only direct-invocable agents may be invoked here");
assert.equal(agentInvokeEnabled(agentProfile, "go", true), false, "a pending mutation must block a second invocation");
assert.equal(agentInvokeEnabled(agentProfile, "go", false), true);

{
  const agentCalls = [];
  const controller = createAgentsPanelController({
    listAgents: async () => ({ agents: [agentProfile] }),
    listAgentRuns: async () => ({ records: [agentRunRecord] }),
    invokeAgent: async (...args) => { agentCalls.push(["invoke", ...args]); return { agent_id: "researcher", status: "awaiting_approval" }; },
    cancelAgent: async (...args) => { agentCalls.push(["cancel", ...args]); return { profile_id: "researcher", cancelled: false }; },
  });
  await controller.load();
  const loaded = controller.snapshot();
  assert.deepEqual(loaded.agents, [agentProfile], "the agent catalog must be unwrapped from its list envelope");
  assert.deepEqual(loaded.runs, [agentRunRecord], "agent runs must be unwrapped from the audit records envelope");
  controller.selectAgent("researcher");
  controller.setPrompt("summarize the readiness report");
  await controller.invoke("researcher", "summarize the readiness report");
  assert.deepEqual(agentCalls, [["invoke", "researcher", "summarize the readiness report"]]);
  const invoked = controller.snapshot();
  assert.equal(invoked.mutationPending, false, "the mutation lock must release after an invocation");
  assert.equal(invoked.notice, "Agent invocation is awaiting approval.");
  assert.equal(invoked.prompt, "", "a completed invocation must clear the prompt draft");
  await controller.cancel("researcher");
  assert.deepEqual(agentCalls[1], ["cancel", "researcher"]);
  assert.equal(controller.snapshot().notice, "No cancellable agent run was found.");
}

{
  const controller = createAgentsPanelController({
    invokeAgent: async () => { throw new Error("agent capability is not authorized"); },
    listAgentRuns: async () => ({ records: [] }),
  });
  await controller.invoke("researcher", "go");
  const failed = controller.snapshot();
  assert.equal(failed.mutationError, "agent capability is not authorized", "a failed invocation must report as an error");
  assert.equal(failed.notice, "", "a failed invocation must not also read as a success notice");
  assert.equal(failed.mutationPending, false);
}

{
  const firstAgents = deferred();
  let agentListCalls = 0;
  const controller = createAgentsPanelController({
    listAgents: () => (agentListCalls++ === 0 ? firstAgents.promise : Promise.resolve({ agents: [agentProfile] })),
  });
  const staleRequest = controller.refreshAgents();
  await controller.refreshAgents();
  firstAgents.resolve({ agents: [] });
  await staleRequest;
  assert.deepEqual(controller.snapshot().agents, [agentProfile], "stale agent responses must not replace a newer catalog");
}

{
  const controller = createAgentsPanelController({
    listAgents: async () => { throw new Error("agent registry is unavailable"); },
  });
  await controller.refreshAgents();
  assert.equal(controller.snapshot().agentsError, "agent registry is unavailable", "an unavailable registry must be surfaced, not hidden");
}

for (const banned of ["innerHTML", "fetch(", "localStorage", "style.display"]) {
  assert.ok(!agentsPanel.includes(banned), `agents panel must not use ${banned}`);
}

for (const relativePath of [
  "../package.json",
  "../src/index.html",
  "../src/api-client.js",
  "../src/main.js",
  "../src/components/appearance-controls.js",
  "../src/components/backend-diagnostics.js",
  "../src/components/settings-panel.js",
  "../src/components/llm-provider-settings.js",
  "../src/components/memory-panel.js",
  "../src/components/actions-panel.js",
  "../src/components/extensions-panel.js",
  "../src/components/agents-panel.js",
  "../src/components/advanced-panel.js",
  "../src/components/resident-voice.js",
  "../src/components/service-status.js",
  "../src/components/desktop-polling.js",
  "../src/style.css",
  "../src-tauri/Cargo.toml",
  "../src-tauri/build.rs",
  "../src-tauri/tauri.conf.json",
  "../src-tauri/src/main.rs",
  "../src-tauri/src/lib.rs",
  "../src-tauri/src/backend.rs",
  "../src-tauri/icons/icon.png",
  "../src-tauri/icons/icon.ico",
]) {
  assert.ok(existsSync(new URL(relativePath, import.meta.url)), `required desktop file missing: ${relativePath}`);
}

assert.deepEqual(tauriConfig.bundle.icon, ["icons/icon.png", "icons/icon.ico"]);
assert.ok(cargoToml.includes("tray-icon"), "Tauri must enable tray-icon support");
assert.ok(lib.includes("TrayIconBuilder"), "Tauri shell must build the tray icon");
for (const label of ["Start Backend", "Stop Backend", "Show Window", "Quit"]) {
  assert.ok(lib.includes(label), `tray menu must include ${label}`);
}
assert.ok(backend.includes("run_backend.py"), "desktop must launch the backend entrypoint");
assert.ok(!`${backend}\n${lib}`.includes("run_jarvis.py"), "desktop must not launch the proving-host entrypoint");
assert.ok(backend.includes('join("cache")'), "desktop must read backend daemon metadata under cache/");
assert.ok(backend.includes("/daemon/status"), "desktop must probe daemon status before spawning");
assert.ok(backend.includes("/daemon/shutdown"), "desktop daemon stop must use the token-protected backend route");
assert.ok(!backend.includes("netstat -ano"), "desktop must not discover unrelated port owners with netstat");
assert.ok(!backend.includes("taskkill"), "desktop must not kill unrelated port owners");

const tokenStart = "/* JARVIS_V7_TOKENS_START */";
const tokenEnd = "/* JARVIS_V7_TOKENS_END */";
assert.equal(style.split("JARVIS_V7_TOKENS_START").length - 1, 1);
assert.equal(style.split("JARVIS_V7_TOKENS_END").length - 1, 1);
assert.ok(style.indexOf(tokenStart) < style.indexOf(tokenEnd));
for (const token of [
  "--color-bg-base",
  "--color-accent",
  "--color-ready",
  "--color-degraded",
  "--color-failed",
  "--color-capture",
  "--color-text-primary",
  "--space-1",
]) {
  assert.ok(style.includes(token), `style token missing: ${token}`);
}
const outsideTokens = style.slice(0, style.indexOf(tokenStart)) + style.slice(style.indexOf(tokenEnd) + tokenEnd.length);
assert.doesNotMatch(outsideTokens, /#[0-9a-fA-F]{3,8}\b/);
for (const rawColorFunction of ["rgb(", "rgba(", "hsl(", "hsla("]) {
  assert.ok(!outsideTokens.includes(rawColorFunction), `raw color function outside token section: ${rawColorFunction}`);
}
for (const selector of [
  '[data-state="LISTENING"]',
  '[data-state="REASONING"]',
  '[data-state="SPEAKING"]',
  '[data-state="DEGRADED"]',
  '[data-state="FAILED"]',
  '[data-capture-state="recording"]',
  '[data-capture-state="processing"]',
  'data-readiness-state="ready"',
  'data-readiness-state="degraded"',
  'data-readiness-state="failed"',
  ".degraded-condition",
  "capture-pulse",
  ".message.user",
  ".message.assistant",
  ".message.system",
  ".message.presence",
]) {
  assert.ok(style.includes(selector), `desktop style contract missing: ${selector}`);
}
assert.ok(!index.includes(" style="), "desktop markup must not use inline styles");
const textForm = index.match(/<form id="text-form"[\s\S]*?<\/form>/)?.[0] || "";
assert.ok(textForm.includes('id="text-input"') && textForm.includes('id="send-button"'));
assert.ok(!textForm.includes('id="search-status"') && !textForm.includes('id="search-stop"'), "search progress must not occupy composer grid cells");
assert.ok(style.includes("grid-template-columns: minmax(220px, 280px) minmax(320px, 1fr) minmax(260px, 340px);"));
for (const selector of [
  ".status-panel",
  ".conversation-panel",
  ".operator-panel",
  ".panel-section",
  ".operator-header",
  ".operator-actions",
  ".settings-panel",
  ".appearance-panel",
]) {
  assert.ok(style.includes(selector), `desktop layout contract missing: ${selector}`);
}
assert.match(style, /\.status-panel\s*{\s*overflow-y:\s*auto;/);
assert.match(style, /\.operator-panel\s*{[\s\S]*overflow:\s*hidden;/);
assert.ok(style.includes("@media (max-width: 820px)"));
assert.ok(!style.includes("@media (max-width: 1180px)"));
assert.ok(!style.includes("grid-template-areas"));
for (const selector of [
  ".advanced-panel",
  ".advanced-panel::backdrop",
  ".advanced-panel-rail",
  '.advanced-panel-rail button[aria-selected="true"]',
  ".advanced-panel-detail",
  ".extensions-panel-layout",
  ".extensions-panel-list",
  ".extensions-panel-detail",
  ".agents-panel",
  "--color-backdrop",
]) {
  assert.ok(style.includes(selector), `advanced-control style contract missing: ${selector}`);
}
for (const dead of [".icon-button", ".operator-trigger-group", ".settings-trigger-group"]) {
  assert.ok(!style.includes(dead), `dead operator trigger-row style must be removed: ${dead}`);
}
assert.ok(
  !style.includes(".status-panel #personality-select"),
  "Personality must share the operator-panel selector sizing once it moves to the right sidebar",
);
for (const snippet of [
  'document.createElement("article")',
  'document.createElement("span")',
  'document.createElement("strong")',
  'document.createElement("p")',
  'bodyEl.textContent = text || "(no text returned)"',
  "entry.append(stampEl, roleEl, bodyEl)",
]) {
  assert.ok(main.includes(snippet), `message rendering contract missing: ${snippet}`);
}
assert.ok(!main.includes("entry.innerHTML"), "message rendering must use DOM text APIs");

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
assert.ok(
  index.indexOf("personality-panel") < index.indexOf("resident-voice-panel"),
  "Personality must render above Resident Voice in the operator panel",
);
assert.ok(
  index.indexOf("advanced-controls-trigger") < index.indexOf('class="panel conversation-panel"'),
  "the advanced-control launch button must sit in the left status sidebar below the status indicators",
);
assert.ok(
  index.indexOf("service-status") < index.indexOf("advanced-controls-trigger"),
  "Backend, Readiness and Services must stay above the advanced-control launch button",
);
assert.ok(!index.includes("operator-trigger-group"), "the single-letter operator trigger row must be gone");
assert.ok(index.includes('<dialog id="advanced-panel"'), "advanced controls must open one dialog surface");
assert.ok(index.includes('id="advanced-panel-rail"'), "the advanced-control dialog must carry a category rail");
assert.ok(index.includes('id="advanced-panel-close"'), "the advanced-control dialog must expose an explicit close control");
for (const category of ["providers", "settings", "memory", "actions", "extensions", "agents"]) {
  assert.ok(
    index.includes(`data-category="${category}"`),
    `advanced-control rail missing category: ${category}`,
  );
  assert.ok(
    index.includes(`id="${category}-panel"`),
    `advanced-control detail pane missing mount: ${category}-panel`,
  );
}
for (const label of ["Providers &amp; Models", "Operator Settings", "Actions &amp; Capabilities", "Agents"]) {
  assert.ok(index.includes(label), `advanced-control rail missing label: ${label}`);
}
assert.ok(
  index.indexOf("<dialog") > index.indexOf("</main>"),
  "the advanced-control dialog must sit outside the overflow-hidden shell",
);
assert.ok(main.includes("showModal()"), "the advanced-control surface must use native modal dismissal and focus handling");
assert.ok(
  main.includes('advancedDialogEl.addEventListener("close"'),
  "Escape, the close button and a backdrop click must all tear down through one close hook",
);
assert.ok(
  main.includes("event.target === advancedDialogEl"),
  "a backdrop click must dismiss the advanced-control surface",
);
assert.ok(main.includes("advancedDialogEl.open"), "the restart badge must reflect whether the advanced surface is showing");
assert.ok(main.includes('aria-selected'), "the rail must mark the showing category");
assert.ok(!main.includes("createOperatorPanelCoordinator"), "category switching must have one owner");
assert.ok(main.includes("createAgentsPanel"), "Agents must be mounted in the desktop surface");
assert.ok(main.includes("openProviderSettings"), "Providers & Models must be mounted as its own category");
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
assert.ok(!main.includes("Default words"), "desktop must not show profile default word count in the compact operator sidebar");
assert.ok(main.includes("personalityDetailEl.textContent"), "desktop must keep compact personality metadata on one rendered line");
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
assert.ok(
  !settingsPanel.includes('querySelectorAll("input, select, button")'),
  "an operator-config save must not blanket-disable another category's controls",
);
assert.ok(!settingsPanel.includes("llm-provider-settings.js"), "Providers & Models must not be nested inside the operator settings form");
assert.equal(restartScopeDisables(["operator"], "operator"), true);
assert.equal(restartScopeDisables(["operator"], "provider"), false, "restart scopes must not leak across categories");
assert.equal(restartScopeDisables(new Set(["provider"]), "provider"), true);
assert.equal(restartScopeDisables(null, "operator"), false);
assert.ok(llmProviderSettings.includes("Model Providers"), "settings must expose Model Providers");
assert.ok(llmProviderSettings.includes("Allow cloud escalation"), "settings must expose cloud escalation authorization");
assert.ok(llmProviderSettings.includes("Test connection"), "settings must expose provider readiness testing");
assert.ok(llmProviderSettings.includes("Remove stored credential"), "settings must expose credential removal");
assert.ok(!llmProviderSettings.includes("innerHTML"), "provider settings must render through DOM text APIs");
assert.ok(llmProviderSettings.includes("openProviderSettings"), "Providers & Models must be mountable as its own advanced-control category");

const builtinManaged = { profile_id: "builtin:managed-llama-cpp", name: "managed llama.cpp", kind: "managed_llama_cpp", builtin: true };
const editableLab = { profile_id: "lab", name: "Lab", kind: "openai_compatible" };
const editableCloud = { profile_id: "cloud", name: "Cloud", kind: "openai", cloud_eligible: true };
const builtinSelection = { primary_profile_id: "builtin:managed-llama-cpp" };
assert.equal(
  defaultEditingProfile([builtinManaged, editableLab], builtinSelection)?.profile_id,
  "lab",
  "the provider editor must open on an editable profile instead of a read-only built-in",
);
assert.equal(
  defaultEditingProfile([builtinManaged, editableLab, editableCloud], builtinSelection, "cloud")?.profile_id,
  "cloud",
  "the acted-on profile must stay selected after a create or update reload",
);
assert.equal(
  defaultEditingProfile([builtinManaged], builtinSelection)?.profile_id,
  "builtin:managed-llama-cpp",
  "with no editable profile the selected built-in is still shown",
);
assert.equal(defaultEditingProfile([], {})?.profile_id, undefined, "an empty catalog must resolve to no profile");
assert.equal(defaultEditingProfile(null, null), null);
assert.ok(
  builtinProfileNotice(builtinManaged).includes("cannot be edited"),
  "a built-in profile must explain why its controls are read-only",
);
assert.equal(builtinProfileNotice(editableLab), "", "an editable profile must not claim to be read-only");
assert.equal(providerRestartDisabled(["operator"]), false, "an operator-config save must not freeze provider controls");
assert.equal(providerRestartDisabled(["provider"]), true);
assert.equal(providerRestartDisabled(new Set(["operator", "provider"])), true);
assert.equal(providerRestartDisabled([]), false);

assert.deepEqual(providerSelectionPayload("primary", "", false, "cloud"), {
  primary_profile_id: "primary",
  local_fallback_profile_id: null,
  cloud_escalation_enabled: false,
  cloud_profile_id: "cloud",
});
assert.deepEqual(
  providerChoiceGroups([
    { profile_id: "managed", kind: "managed_llama_cpp", cloud_eligible: false },
    { profile_id: "private-compatible", kind: "openai_compatible", cloud_eligible: false },
    { profile_id: "public-compatible", kind: "openai_compatible", cloud_eligible: true },
    { profile_id: "openai", kind: "openai", cloud_eligible: true },
  ]),
  { local: ["managed", "private-compatible"], cloud: ["public-compatible", "openai"] },
);

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
    listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
    appendChild(child) {
      child.parentElement = this;
      this.children.push(child);
      return child;
    },
    append(...children) {
      for (const child of children) this.appendChild(child);
    },
    replaceChildren(...children) {
      this.children = [];
      for (const child of children) this.appendChild(child);
    },
    setAttribute(name, value) { this[name] = value; },
    focus() { this.focused = true; },
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

{
  const capabilities = [
    {
      capability_id: "memory-policy-update",
      effect_class: "local_write",
      readiness: "ready",
      availability: "available",
      authorization_rule: "allow",
      approval_mode: "same_turn",
      execution_owner: "backend.app.services.memory_service.MemoryService",
      unavailable_explanation: "",
      executable: true,
      input_schema: {
        type: "object",
        properties: { automatic_curation_enabled: { type: "boolean" }, expected_revision: { type: "integer" } },
        required: ["automatic_curation_enabled", "expected_revision"],
      },
    },
    {
      capability_id: "search-public-web",
      effect_class: "external_read",
      readiness: "ready",
      availability: "available",
      authorization_rule: "allow",
      approval_mode: "turn_boundary",
      execution_owner: "backend.app.services.search_service.SearchService",
      unavailable_explanation: "",
      executable: false,
      input_schema: { type: "object", properties: {} },
    },
  ];
  let proposed = null;
  const container = createElement("div");
  const panel = createActionsPanel(container, {
    getActionCapabilities: async () => ({
      capabilities,
      problems: [{ capability_id: "agent-invoke-coder", reason: "privileged_execution capabilities must declare boundaries" }],
    }),
    getPendingActions: async () => ({ pending: [] }),
    getActionAudit: async () => ({ records: [{ kind: "execution_result", capability_id: "memory-policy-update", proposal_id: "p3", recorded_at: "now" }] }),
    getActionStatus: async () => ({ proposal_id: "p3", capability_id: "memory-policy-update", status: "success", outcome: "allowed", reason: "ok", arguments: {} }),
    proposeAction: async (payload) => {
      proposed = payload;
      return { proposal_id: "p3", capability_id: "memory-policy-update", status: "success", outcome: "allowed", reason: "ok", arguments: {} };
    },
  });
  await panel.open();

  const buttons = findElements(container, (node) => node.tagName === "button");
  const proposeTrigger = buttons.find((node) => node.textContent === "Propose");
  assert.ok(proposeTrigger, "a drivable capability must offer a Propose control");
  assert.equal(
    buttons.filter((node) => node.textContent === "Propose").length,
    1,
    "a turn-boundary capability must not offer a Propose control",
  );
  assert.ok(
    findElement(container, (node) => String(node.textContent).includes("agent-invoke-coder")),
    "a descriptor the registry refused must be explained in the panel",
  );
  assert.ok(
    findElement(container, (node) => String(node.textContent).includes("backend.app.services.search_service.SearchService")),
    "a capability with no proposable executor must name its owner",
  );

  proposeTrigger.listeners.click();
  const form = findElement(container, (node) => node.className === "actions-propose");
  assert.ok(form, "the Propose control must open a form built from the declared input schema");
  const controls = findElements(container, (node) => node.tagName === "input" || node.tagName === "textarea");
  const byName = Object.fromEntries(controls.map((node) => [node.name, node]));
  assert.deepEqual(
    Object.keys(byName),
    ["automatic_curation_enabled", "expected_revision", "reason"],
    "the form must render one control per declared property plus the reason",
  );
  assert.equal(byName.automatic_curation_enabled.type, "checkbox");
  assert.equal(byName.expected_revision.type, "number");
  byName.automatic_curation_enabled.listeners.change({ target: { checked: true } });
  byName.expected_revision.listeners.input({ target: { value: "4" } });
  byName.reason.listeners.input({ target: { value: "operator enabled curation" } });
  await form.listeners.submit({ preventDefault() {} });

  assert.deepEqual(
    proposed,
    {
      capabilityId: "memory-policy-update",
      actionArguments: { automatic_curation_enabled: true, expected_revision: 4 },
      reason: "operator enabled curation",
    },
    "the rendered form must originate the action with its typed arguments",
  );
  const auditStatus = findElements(container, (node) => node.tagName === "button" && node.textContent === "Status");
  assert.ok(auditStatus.length >= 1, "an audit record must be inspectable from the rendered panel");
  panel.close();
}

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

const contractsController = createMemoryPanelController({
  getMemoryLayers: () =>
    Promise.resolve({
      layers: [
        { layer: "semantic_memory", implementation_state: "implemented" },
        { layer: "procedural_memory", implementation_state: "defined_next" },
        { layer: "cross_device_shared_memory", implementation_state: "decision_required" },
      ],
      source_artifact_erasure_scope: "Source turn and session artifacts are separate.",
    }),
  getArtifactRetentionPolicy: () =>
    Promise.resolve({
      source_artifact_owner: "backend/app/artifacts",
      physical_erasure_available: false,
      source_artifact_erasure_scope: "Physical erasure is a separate action.",
    }),
});
await contractsController.refreshContracts();
assert.equal(
  contractsController.snapshot().layers.layers[1].implementation_state,
  "defined_next",
  "memory contract refresh must retain backend layer states",
);
assert.equal(
  contractsController.snapshot().retentionPolicy.source_artifact_owner,
  "backend/app/artifacts",
  "memory contract refresh must retain retention owner",
);

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
assert.equal(
  formatCurationResult({
    reason_code: "review_only_candidates_resolved",
    candidates_proposed: 3,
    candidates_rejected: 1,
    active_records_created: 0,
    pending_review_created: 2,
    records_reinforced: 0,
    records_superseded_or_disputed: 0,
    duplicate_noops: 1,
    failure_count: 0,
  }),
  "review_only_candidates_resolved · proposed 3 · pending review 2 · active 0 · rejected 1 · duplicates 1 · reinforced 0 · superseded/disputed 0 · failures 0",
  "desktop curation outcome must render only the structured backend result",
);
assert.equal(
  formatCurationResult(null),
  "",
  "desktop must not infer a processor result when backend truth is absent",
);

const panelEvents = [];
let dismissals = 0;
function advancedCategory(id, openInitially = false) {
  let open = openInitially;
  return {
    id,
    isOpen: () => open,
    open: async () => {
      panelEvents.push(`open-${id}`);
      open = true;
    },
    close: () => {
      panelEvents.push(`close-${id}`);
      open = false;
    },
  };
}
const advancedCategories = [
  advancedCategory("providers"),
  advancedCategory("settings", true),
  advancedCategory("memory"),
  advancedCategory("actions"),
  advancedCategory("extensions"),
  advancedCategory("agents"),
];
const coordinator = createAdvancedPanelCoordinator({
  categories: advancedCategories,
  dismiss: () => {
    dismissals += 1;
    coordinator.closeActive();
  },
});
assert.deepEqual(
  coordinator.categoryIds(),
  ["providers", "settings", "memory", "actions", "extensions", "agents"],
  "every advanced-control category must be registered, including Agents and Providers & Models",
);
assert.equal(coordinator.activeCategoryId(), "settings", "the rail must report which category is showing");

await coordinator.openCategory("memory");
assert.deepEqual(panelEvents, ["close-settings", "open-memory"], "memory open must deterministically close settings first");
assert.equal(coordinator.activeCategoryId(), "memory");
panelEvents.length = 0;

await coordinator.openCategory("agents");
assert.deepEqual(panelEvents, ["close-memory", "open-agents"], "a rail is single-select, so switching must close the previous category");
panelEvents.length = 0;

await coordinator.openCategory("agents");
assert.deepEqual(panelEvents, [], "re-selecting the showing category must not remount it");
await coordinator.openCategory("nonexistent");
assert.deepEqual(panelEvents, [], "an unknown category must be ignored rather than closing the surface");

coordinator.requestClose();
assert.deepEqual(panelEvents, ["close-agents"], "dismissal must close whichever category is showing");
assert.equal(dismissals, 1);
assert.equal(coordinator.activeCategoryId(), "", "nothing may stay mounted after dismissal");
panelEvents.length = 0;

coordinator.requestClose();
assert.deepEqual(panelEvents, [], "dismissing an already-dismissed surface must be a no-op");

// A category's own Close button reports through onClose, which asks the host to dismiss. That
// report must not re-enter as a second dismissal, and it must not fire during a rail switch.
const reentrantEvents = [];
let reentrantDismissals = 0;
const reentrant = [];
function reentrantCategory(id, openInitially = false) {
  let open = openInitially;
  return {
    id,
    isOpen: () => open,
    open: async () => {
      reentrantEvents.push(`open-${id}`);
      open = true;
    },
    close: () => {
      reentrantEvents.push(`close-${id}`);
      open = false;
      reentrantCoordinator.requestClose();
    },
  };
}
reentrant.push(reentrantCategory("memory", true), reentrantCategory("agents"));
const reentrantCoordinator = createAdvancedPanelCoordinator({
  categories: reentrant,
  dismiss: () => {
    reentrantDismissals += 1;
    reentrantCoordinator.closeActive();
  },
});
await reentrantCoordinator.openCategory("agents");
assert.deepEqual(reentrantEvents, ["close-memory", "open-agents"], "a category switch must not dismiss the whole surface");
assert.equal(reentrantDismissals, 0, "closing a category to switch rails is not a dismissal");
reentrantEvents.length = 0;
reentrantCoordinator.closeActive();
assert.deepEqual(reentrantEvents, ["close-agents"], "teardown must close each category exactly once");
assert.equal(reentrantDismissals, 0, "an onClose report during teardown must not re-enter as a new dismissal");

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
assert.ok(index.includes('id="memory-panel"'), "operator area must include one hidden Memory panel");

for (const command of [
  "get_action_capabilities",
  "get_pending_actions",
  "get_action_audit",
  "propose_action",
  "get_action_status",
  "decide_action",
  "cancel_action",
]) {
  assert.ok(
    apiClient.includes(`invokeMemory(invoke, "${command}"`),
    `API client must use Tauri command ${command}`,
  );
  assert.ok(lib.includes(command), `Tauri handler must register ${command}`);
}

for (const route of [
  "/actions/capabilities",
  "/actions/pending",
  "/actions/audit",
  "/actions/propose",
  "/actions/{proposal_id}",
  "/actions/{proposal_id}/decision",
  "/actions/{proposal_id}/cancel",
]) {
  assert.ok(backend.includes(route), `backend bridge must include ${route}`);
}

for (const field of [
  "capability_id",
  "effect_class",
  "approval_mode",
  "authorization_rule",
  "unavailable_explanation",
  "executable",
  "proposal_id",
  "approval_id",
  "expires_at",
  "outcome",
  "execution",
  "cancelled",
]) {
  assert.ok(
    actionsPanel.includes(field) || apiClient.includes(field),
    `actions surface must include ${field}`,
  );
}

assert.ok(!actionsPanel.includes("innerHTML"), "actions panel must render backend text without innerHTML");
assert.ok(!actionsPanel.includes("fetch("), "actions panel must not call backend HTTP directly");
assert.ok(!actionsPanel.includes("localStorage"), "actions state must not be persisted in renderer storage");
assert.ok(
  !actionsPanel.includes("APPROVABLE_STATES"),
  "renderer must not duplicate backend approval policy",
);
assert.ok(
  !actionsPanel.includes(".has(pending.status)"),
  "approval availability must not be inferred from a status string",
);

assert.ok(index.includes('id="actions-panel"'), "operator area must include one hidden Actions panel");

{
  const pendingPage = (ids) => ({ pending: ids.map((id) => ({ proposal_id: id, capability_id: "memory-record-forget", approval_id: "a1", arguments: {}, reason: "r", expires_at: "later" })) });
  const slow = deferred();
  const fast = deferred();
  let call = 0;
  const controller = createActionsPanelController({
    getPendingActions: () => (call++ === 0 ? slow.promise : fast.promise),
  });
  const first = controller.refreshPending();
  const second = controller.refreshPending();
  fast.resolve(pendingPage(["new"]));
  await second;
  slow.resolve(pendingPage(["old"]));
  await first;
  assert.equal(
    controller.snapshot().pending[0].proposal_id,
    "new",
    "a slow pending response must not overwrite a newer one",
  );
}

{
  const controller = createActionsPanelController({
    getPendingActions: async () => ({ pending: [] }),
    getActionAudit: async () => ({ records: [] }),
    getActionStatus: async () => ({ proposal_id: "p1", status: "success" }),
    decideAction: async () => ({ proposal_id: "p1", status: "success", outcome: "allowed" }),
  });
  await controller.decide("p1", "approved");
  const snapshot = controller.snapshot();
  assert.equal(snapshot.mutationPending, false, "the mutation lock must release after a decision");
  assert.equal(snapshot.notice, "Action approved.", "an approval must report its outcome");
}

{
  const conflict = Object.assign(new Error("already decided"), {
    status: 409,
    detail: { error: "already_decided", message: "this action has already been decided" },
  });
  let reloaded = 0;
  const controller = createActionsPanelController({
    getPendingActions: async () => {
      reloaded += 1;
      return { pending: [] };
    },
    getActionAudit: async () => ({ records: [] }),
    getActionStatus: async () => ({ proposal_id: "p1", status: "success" }),
    decideAction: async () => {
      throw conflict;
    },
  });
  await controller.decide("p1", "approved");
  const snapshot = controller.snapshot();
  assert.ok(
    snapshot.conflict.includes("already been decided"),
    "a rejected decision must surface the backend reason",
  );
  assert.ok(snapshot.conflict.includes("reloaded"), "a conflict must state that truth was reloaded");
  assert.ok(reloaded > 0, "a conflict must reload backend state instead of guessing");
}

{
  let cancels = 0;
  const handlers = {
    getPendingActions: async () => ({ pending: [] }),
    getActionAudit: async () => ({ records: [] }),
    getActionStatus: async () => ({ proposal_id: "p1", status: "cancelled" }),
    cancelAction: async () => {
      cancels += 1;
      return { proposal_id: "p1", cancelled: true };
    },
  };
  const declined = createActionsPanelController(handlers);
  await declined.cancel("p1", () => Promise.resolve(false));
  assert.equal(cancels, 0, "a declined cancellation must not reach the backend");

  const confirmed = createActionsPanelController(handlers);
  await confirmed.cancel("p1", () => Promise.resolve(true));
  assert.equal(cancels, 1, "a confirmed cancellation must reach the backend exactly once");
}

{
  const controller = createActionsPanelController({
    getActionCapabilities: async () => ({
      capabilities: [
        {
          capability_id: "search-public-web",
          availability: "disabled",
          readiness: "unavailable",
          unavailable_explanation: "No web search provider is enabled.",
          effect_class: "external_read",
          authorization_rule: "allow",
        },
      ],
    }),
  });
  await controller.refreshCapabilities();
  const capability = controller.snapshot().capabilities.capabilities[0];
  assert.equal(
    capability.unavailable_explanation,
    "No web search provider is enabled.",
    "the panel must retain the backend explanation verbatim",
  );
}

assert.equal(actionApprovalEnabled({ proposal_id: "p1" }, false), true);
assert.equal(actionApprovalEnabled({ proposal_id: "p1" }, true), false, "an in-flight mutation must disable approval");
assert.equal(actionApprovalEnabled(null, false), false);

for (const [execution, expected] of [
  [null, "idle"],
  [{ status: "success" }, "succeeded"],
  [{ status: "failure" }, "failed"],
  [{ status: "cancelled" }, "cancelled"],
]) {
  assert.equal(executionActivityState(execution), expected);
}

for (const [capability, expected] of [
  [{ availability: "available", readiness: "ready" }, "ready"],
  [{ availability: "available", readiness: "degraded" }, "degraded"],
  [{ availability: "disabled", readiness: "unavailable" }, "blocked"],
]) {
  assert.equal(capabilityActivityState(capability), expected);
}

assert.equal(
  formatCapabilityRisk({ effect_class: "destructive_action", authorization_rule: "requires_approval" }),
  "destructive_action · approval required",
);

assert.equal(
  formatCapabilityApproval({ approval_mode: "turn_boundary" }),
  "approved in conversation",
  "a turn-boundary capability must not look operator-drivable",
);
assert.equal(formatCapabilityApproval({ approval_mode: "same_turn" }), "approved here");

// Only backend-reported facts may gate the propose control.
assert.equal(
  proposeEnabled({ executable: true, availability: "available", approval_mode: "same_turn" }, false),
  true,
);
for (const capability of [
  { executable: false, availability: "available", approval_mode: "same_turn" },
  { executable: true, availability: "disabled", approval_mode: "same_turn" },
  { executable: true, availability: "available", approval_mode: "turn_boundary" },
]) {
  assert.equal(proposeEnabled(capability, false), false, "an undrivable capability must not offer Propose");
}
assert.equal(
  proposeEnabled({ executable: true, availability: "available", approval_mode: "same_turn" }, true),
  false,
  "an in-flight mutation must disable proposing",
);

{
  const schema = {
    type: "object",
    properties: {
      fact_id: { type: "string" },
      expected_revision: { type: "integer" },
      endpoint: { type: ["string", "null"] },
      enabled: { type: "boolean" },
      fields: { type: "object" },
    },
    required: ["fact_id", "expected_revision", "endpoint"],
  };
  const fields = capabilityArgumentFields(schema);
  assert.deepEqual(
    fields.map((field) => [field.name, field.type, field.nullable, field.required]),
    [
      ["fact_id", "string", false, true],
      ["expected_revision", "integer", false, true],
      ["endpoint", "string", true, true],
      ["enabled", "boolean", false, false],
      ["fields", "object", false, false],
    ],
  );
  assert.deepEqual(
    coerceArguments(fields, {
      fact_id: "fact-1",
      expected_revision: "3",
      endpoint: "",
      enabled: true,
      fields: '{"USE_DDGS":"true"}',
    }),
    {
      fact_id: "fact-1",
      expected_revision: 3,
      endpoint: null,
      enabled: true,
      fields: { USE_DDGS: "true" },
    },
    "typed arguments must reach the backend as their declared types",
  );
  assert.throws(
    () => coerceArguments(fields, { fields: "not json" }),
    /fields must be valid JSON/,
    "a malformed structured argument must be reported before it is sent",
  );
}

{
  let sent = null;
  const controller = createActionsPanelController({
    getPendingActions: async () => ({ pending: [] }),
    getActionAudit: async () => ({ records: [] }),
    getActionStatus: async () => ({ proposal_id: "p9", status: "success" }),
    proposeAction: async (payload) => {
      sent = payload;
      return { proposal_id: "p9", capability_id: "memory-policy-update", status: "success", outcome: "allowed" };
    },
  });
  const capability = {
    capability_id: "memory-policy-update",
    executable: true,
    availability: "available",
    approval_mode: "same_turn",
    input_schema: {
      type: "object",
      properties: { automatic_curation_enabled: { type: "boolean" }, expected_revision: { type: "integer" } },
      required: ["automatic_curation_enabled", "expected_revision"],
    },
  };
  controller.selectCapability(capability.capability_id);
  assert.equal(controller.snapshot().proposeCapabilityId, "memory-policy-update");
  controller.setProposeValue("automatic_curation_enabled", true);
  controller.setProposeValue("expected_revision", "2");
  controller.setProposeReason("operator enabled curation");
  await controller.submitPropose(capability);
  assert.deepEqual(
    sent,
    {
      capabilityId: "memory-policy-update",
      actionArguments: { automatic_curation_enabled: true, expected_revision: 2 },
      reason: "operator enabled curation",
    },
    "the panel must originate an action with its typed arguments",
  );
  const snapshot = controller.snapshot();
  assert.equal(snapshot.notice, "Action proposed.");
  assert.equal(snapshot.proposeCapabilityId, "", "a proposed action must clear its draft");
  assert.equal(snapshot.detail.proposal_id, "p9", "a proposed action must be inspectable straight away");
}

{
  let sent = 0;
  const controller = createActionsPanelController({
    proposeAction: async () => { sent += 1; return { proposal_id: "p1" }; },
  });
  const capability = {
    capability_id: "operator-config-write",
    input_schema: { type: "object", properties: { fields: { type: "object" } }, required: ["fields"] },
  };
  controller.setProposeValue("fields", "{oops}");
  await controller.submitPropose(capability);
  assert.equal(sent, 0, "a malformed argument must never reach the backend");
  assert.match(controller.snapshot().proposeError, /fields must be valid JSON/);
}

assert.ok(
  actionsPanel.includes("problems"),
  "the capability catalog must report descriptors it could not register",
);
assert.ok(
  !actionsPanel.includes("No application-owned handler is wired."),
  "a capability driven by its own operator surface must not read as broken",
);
assert.ok(
  actionsPanel.includes("state.actions.selectProposal(record.proposal_id)"),
  "an audit record must be inspectable",
);

for (const command of [
  "get_extensions",
  "get_extension_errors",
  "get_extension_detail",
  "get_extension_body",
  "set_extension_state",
]) {
  assert.ok(
    apiClient.includes(`invokeMemory(invoke, "${command}"`),
    `API client must use Tauri command ${command}`,
  );
  assert.ok(lib.includes(command), `Tauri handler must register ${command}`);
}

for (const route of [
  "/extensions",
  "/extensions/errors",
  "/extensions/{extension_id}",
  "/extensions/{extension_id}/body",
  "/extensions/{extension_id}/state",
]) {
  assert.ok(backend.includes(route), `backend bridge must include ${route}`);
}

for (const field of [
  "extension_id",
  "family",
  "version",
  "provenance",
  "trust",
  "readiness",
  "availability",
  "unavailable_explanation",
  "collisions",
  "metadata_claims",
  "requested_capabilities",
  "body_available",
]) {
  assert.ok(
    extensionsPanel.includes(field) || apiClient.includes(field),
    `extension surface must include ${field}`,
  );
}

assert.ok(!extensionsPanel.includes("innerHTML"), "extensions panel must render backend text without innerHTML");
assert.ok(!extensionsPanel.includes("fetch("), "extensions panel must not call backend HTTP directly");
assert.ok(!extensionsPanel.includes("localStorage"), "extension state must not be persisted in renderer storage");
assert.ok(
  !extensionsPanel.includes("TRUST_TIERS"),
  "renderer must not duplicate backend trust policy",
);
assert.ok(
  !extensionsPanel.includes(".has(extension.family)"),
  "extension availability must not be inferred from its family",
);

assert.ok(index.includes('id="extensions-panel"'), "operator area must include one hidden Extensions panel");

{
  const page = (ids) => ({
    extensions: ids.map((id) => ({
      extension_id: id, family: "skill", local_id: id, version: "1", display_name: id,
      source: "s", provenance: "p", trust: "external", state: "enabled",
      readiness: "ready", availability: "available", unavailable_explanation: "",
      dependencies: [], collisions: [], metadata_claims: {},
    })),
    families: { skill: ids.length },
  });
  const slow = deferred();
  const fast = deferred();
  let call = 0;
  const controller = createExtensionsPanelController({
    getExtensions: () => (call++ === 0 ? slow.promise : fast.promise),
  });
  const first = controller.refreshCatalog();
  const second = controller.refreshCatalog();
  fast.resolve(page(["skill:new"]));
  await second;
  slow.resolve(page(["skill:old"]));
  await first;
  assert.equal(
    controller.snapshot().catalog.extensions[0].extension_id,
    "skill:new",
    "a slow catalog response must not overwrite a newer one",
  );
}

{
  let calls = 0;
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({ extension_id: "skill:notes", state: "disabled", revision: 2 }),
    setExtensionState: async (id, next, revision) => {
      calls += 1;
      assert.equal(revision, null, "the first change submits the revision it was shown");
      return { extension_id: id, state: next, revision: 1 };
    },
  });
  await controller.setState("skill:notes", "disabled");
  const snapshot = controller.snapshot();
  assert.equal(calls, 1, "a state change must reach the backend exactly once");
  assert.equal(snapshot.mutationPending, false, "the mutation lock must release");
  assert.equal(snapshot.notice, "Extension disabled.");
}

{
  const conflict = Object.assign(new Error("stale"), {
    status: 409,
    detail: { error: "conflict", message: "stale extension overlay revision", current_revision: 3 },
  });
  let reloaded = 0;
  const controller = createExtensionsPanelController({
    getExtensions: async () => {
      reloaded += 1;
      return { extensions: [], families: {} };
    },
    getExtensionDetail: async () => ({ extension_id: "skill:notes", state: "enabled", revision: 3 }),
    setExtensionState: async () => {
      throw conflict;
    },
  });
  await controller.setState("skill:notes", "disabled");
  const snapshot = controller.snapshot();
  assert.ok(snapshot.conflict.includes("stale extension overlay revision"));
  assert.ok(snapshot.conflict.includes("reloaded"), "a conflict must state that truth was reloaded");
  assert.ok(reloaded > 0, "a conflict must reload backend state instead of guessing");
}

{
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({
      extensions: [
        {
          extension_id: "search_provider:searxng", family: "search_provider", local_id: "searxng",
          version: "0", display_name: "searxng", source: "s", provenance: "p",
          trust: "application", state: "disabled", readiness: "unavailable",
          availability: "disabled",
          unavailable_explanation: "No web search provider is enabled.",
          dependencies: [], collisions: [], metadata_claims: {},
        },
      ],
      families: { search_provider: 1 },
    }),
  });
  await controller.refreshCatalog();
  assert.equal(
    controller.snapshot().catalog.extensions[0].unavailable_explanation,
    "No web search provider is enabled.",
    "the panel must retain the backend explanation verbatim",
  );
}

{
  const controller = createExtensionsPanelController({
    getExtensionDetail: async () => ({ extension_id: "skill:notes", body_available: true }),
    getExtensionBody: async () => ({ extension_id: "skill:notes", body: "the body" }),
  });
  await controller.selectExtension("skill:notes");
  assert.equal(controller.snapshot().body, "", "a body must not load during selection");
  await controller.loadBody("skill:notes");
  assert.equal(controller.snapshot().body, "the body", "a body loads only when asked for");
}

assert.equal(extensionStateEnabled({ extension_id: "skill:notes", state: "enabled" }, false), true);
assert.equal(extensionStateEnabled({ extension_id: "skill:notes", state: "enabled" }, true), false);
assert.equal(
  extensionStateEnabled({ extension_id: "skill:notes", state: "retired" }, false),
  false,
  "a retired extension must not offer state controls",
);

for (const [extension, expected] of [
  [null, "idle"],
  [{ state: "enabled", availability: "available", readiness: "ready" }, "ready"],
  [{ state: "enabled", availability: "available", readiness: "degraded" }, "degraded"],
  [{ state: "disabled", availability: "disabled", readiness: "unavailable" }, "blocked"],
  [{ state: "retired", availability: "available", readiness: "ready" }, "retired"],
]) {
  assert.equal(extensionActivityState(extension), expected);
}

assert.equal(
  formatExtensionOrigin({ family: "skill", trust: "external", version: "2" }),
  "skill · external · v2",
);

assert.deepEqual(
  requestedCapabilities({ metadata_claims: { requested_capabilities: { ids: ["search-public-web"], trusted: false } } }),
  ["search-public-web"],
);
assert.deepEqual(requestedCapabilities({ metadata_claims: {} }), []);
assert.ok(extensionsPanel.includes("extensions-panel-layout"), "extensions must render list and detail in separate columns");
assert.ok(!memoryPanel.includes('textContent = "Close"'), "advanced Memory must rely on the dialog Close button");
assert.ok(!actionsPanel.includes('textContent = "Close"'), "advanced Actions must rely on the dialog Close button");
assert.ok(!extensionsPanel.includes('textContent = "Close"'), "advanced Extensions must rely on the dialog Close button");
assert.ok(!agentsPanel.includes('textContent = "Close"'), "advanced Agents must rely on the dialog Close button");

console.log("desktop static, advanced-control, memory, action, extension, and agent behavior checks passed");

{
  // OAuth: the backend holds the verifier and state; the desktop carries only the code back.
  const calls = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({ extension_id: "mcp:probe", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => ({ operations: [], snapshot: null }),
    getExtensionRuns: async () => ({ runs: [] }),
    getExtensionOauth: async () => ({ configured: true, authorized: false }),
    startExtensionOauth: async (extensionId) => {
      calls.push(["start", extensionId]);
      return { authorization_url: "https://auth.test/authorize?x=1", state: "server-state" };
    },
    completeExtensionOauth: async (extensionId, code, oauthState) => {
      calls.push(["complete", extensionId, code, oauthState]);
      return { authorized: true };
    },
  });
  await controller.selectExtension("mcp:probe");
  assert.equal(controller.snapshot().oauthStatus.configured, true);

  await controller.startOauth("mcp:probe");
  const pending = controller.snapshot().oauth;
  assert.equal(pending.url, "https://auth.test/authorize?x=1");
  assert.equal(pending.state, "server-state");

  await controller.completeOauth("mcp:probe", "the-code");
  assert.deepEqual(calls, [
    ["start", "mcp:probe"],
    ["complete", "mcp:probe", "the-code", "server-state"],
  ]);
  assert.equal(controller.snapshot().oauth, null);
}

{
  // Completing without a started flow must not invent a state value.
  let completed = 0;
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    completeExtensionOauth: async () => {
      completed += 1;
      return { authorized: true };
    },
  });
  await controller.completeOauth("mcp:probe", "the-code");
  assert.equal(completed, 0, "no authorization in progress must not reach the backend");
  assert.ok(controller.snapshot().detailError.includes("No authorization"));
}

{
  // Cancelling a run is confirmed, and declining leaves the run alone.
  let cancelled = 0;
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionRuns: async () => ({ runs: [] }),
    cancelAction: async () => {
      cancelled += 1;
    },
  });
  await controller.cancel("proposal-1", async () => false);
  assert.equal(cancelled, 0, "a declined confirmation must not cancel the run");
  await controller.cancel("proposal-1", async () => true);
  assert.equal(cancelled, 1);
}

{
  // The MCP credential form must not depend on discovered operations: a server that
  // demands authorization before discovery has none yet.
  const source = readFileSync(new URL("../src/components/extensions-panel.js", import.meta.url), "utf8");
  const credentialAt = source.indexOf('appendText(credential, "Credential"');
  const guardAt = source.indexOf("if (state.runtime?.operations?.length)");
  assert.ok(credentialAt > 0 && guardAt > 0);
  const between = source.slice(guardAt, credentialAt);
  assert.ok(
    between.includes('if (detail.family === "mcp")'),
    "the credential form must sit outside the operations guard",
  );
}

{
  const client = readFileSync(new URL("../src/api-client.js", import.meta.url), "utf8");
  for (const command of ["get_extension_oauth", "start_extension_oauth", "complete_extension_oauth"]) {
    assert.ok(client.includes(command), `api-client must expose ${command}`);
  }
  const panel = readFileSync(new URL("../src/components/extensions-panel.js", import.meta.url), "utf8");
  assert.ok(!panel.includes("code_verifier"), "the desktop must never handle a PKCE verifier");
}
