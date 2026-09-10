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
  proposeTriggerLabel,
  executionActivityState,
  formatCapabilityApproval,
  formatCapabilityRisk,
} from "../src/components/actions-panel.js";
import {
  createExtensionsPanel,
  createExtensionsPanelController,
  extensionActivityState,
  extensionStateEnabled,
  formatExtensionOrigin,
  formatPromptMessages,
  formatResourceContents,
  formatRunStarted,
  operationDisplayName,
  operationKind,
  operationShortLabel,
  operationSubmitLabel,
  parseAllowlist,
  parseCommandLines,
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

{
  // Invoking an operation such as MCP "discover" changes the extension's own runtime
  // detail (health, discovered tools/resources/prompts), so a completed invocation must
  // refresh what is displayed instead of leaving stale health on screen.
  let runtimeFetches = 0;
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({ extension_id: "mcp:weather", family: "mcp" }),
    getExtensionRuntime: async () => { runtimeFetches += 1; return { operations: [], snapshot: { health: "ready" } }; },
    invokeExtension: async () => ({ status: "success" }),
    getExtensionRuns: async () => ({ runs: [] }),
  });
  await controller.selectExtension("mcp:weather");
  assert.equal(runtimeFetches, 1, "selecting an extension must load its runtime once");
  await controller.invoke("mcp:weather", "extension-abc123", {});
  assert.equal(runtimeFetches, 2, "a completed invocation on the selected extension must refresh its runtime");
  assert.equal(controller.snapshot().runtime.snapshot.health, "ready");
}

{
  // An approval-gated invocation has not run yet, so there is nothing new to refresh.
  let runtimeFetches = 0;
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({ extension_id: "tool:writer", family: "tool" }),
    getExtensionRuntime: async () => { runtimeFetches += 1; return { operations: [] }; },
    invokeExtension: async () => ({ status: "awaiting_approval" }),
    getExtensionRuns: async () => ({ runs: [] }),
  });
  await controller.selectExtension("tool:writer");
  assert.equal(runtimeFetches, 1);
  await controller.invoke("tool:writer", "extension-def456", {});
  assert.equal(runtimeFetches, 1, "an awaiting-approval invocation must not trigger a runtime refresh");
}

{
  // A timeout or cancellation can leave the backend unable to tell whether a call
  // already ran on the far side - the notice must warn against repeating it rather than
  // reading like an ordinary completed invocation.
  const controller = createExtensionsPanelController({
    invokeExtension: async () => ({ status: "outcome_unknown" }),
    getExtensionRuns: async () => ({ runs: [] }),
  }, () => undefined);
  await controller.invoke("mcp:server", "capability", {});
  assert.equal(
    controller.snapshot().notice,
    "Outcome unknown - the call may already have run; check before repeating it.",
  );
}

assert.equal(operationDisplayName({ name: "discover" }), "Discover tools and resources");
assert.equal(operationDisplayName({ name: "tool:get_forecast" }), "tool:get_forecast");
assert.equal(operationSubmitLabel({ name: "discover" }), "Discover");
assert.equal(operationSubmitLabel({ name: "tool:get_forecast" }), "Invoke");
assert.equal(operationSubmitLabel({ name: "resource:file:///notes.txt" }), "Read", "a resource has no arguments to fill in, so it is read, not invoked");
assert.equal(operationSubmitLabel({ name: "prompt:summarize" }), "Get prompt");
assert.equal(operationSubmitLabel({ name: "run" }), "Invoke", "a non-MCP operation keeps the generic verb");

assert.equal(formatRunStarted(null), "—");
assert.equal(formatRunStarted("not a date"), "not a date", "an unparseable timestamp must still display something rather than \"Invalid Date\"");
assert.equal(
  formatRunStarted("2026-09-08T10:32:00.000Z"),
  new Date("2026-09-08T10:32:00.000Z").toLocaleTimeString(),
);

assert.equal(operationKind({ name: "discover" }), "discover");
assert.equal(operationKind({ name: "tool:get_forecast" }), "tool");
assert.equal(operationKind({ name: "resource:file:///notes.txt" }), "resource");
assert.equal(operationKind({ name: "prompt:summarize" }), "prompt");
assert.equal(operationKind({ name: "run" }), "other", "a non-MCP operation must not be miscategorized");
assert.equal(operationKind({ name: "prompt" }), "other", "an ACP operation literally named prompt must not collide with the MCP prompt group");

assert.equal(operationShortLabel({ name: "tool:get_forecast" }), "get_forecast");
assert.equal(operationShortLabel({ name: "resource:file:///notes.txt" }), "file:///notes.txt", "only the first colon marks the group prefix");
assert.equal(operationShortLabel({ name: "prompt:summarize" }), "summarize");
assert.equal(operationShortLabel({ name: "run" }), "run", "a non-grouped operation keeps its plain display name");

{
  // Discovered tools, resources, and prompts must render as separate labeled groups, not
  // one flat "Operations" list mixing internal capability shapes together.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({ extension_id: "mcp:weather", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => ({
      operations: [
        { name: "discover", capability_id: "extension-discover", input_schema: { type: "object", properties: {} }, available: true },
        { name: "tool:get_forecast", capability_id: "extension-tool1", input_schema: { type: "object", properties: {} }, available: true },
        { name: "resource:file:///notes.txt", capability_id: "extension-res1", input_schema: { type: "object", properties: {} }, available: true },
        { name: "prompt:summarize", capability_id: "extension-prompt1", input_schema: { type: "object", properties: {} }, available: true },
      ],
      snapshot: {},
    }),
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:weather");

  const headings = findElements(container, (node) => node.tagName === "h4").map((node) => node.textContent);
  assert.deepEqual(headings, ["Tools", "Resources", "Prompts"], "discovered kinds must render as their own labeled groups, with no generic Operations heading when every operation is already grouped");
  const strongLabels = findElements(container, (node) => node.tagName === "strong").map((node) => node.textContent);
  assert.ok(strongLabels.includes("Discover tools and resources"));
  assert.ok(strongLabels.includes("get_forecast"), "a grouped operation must render its short name, not the internal tool: prefix");
  assert.ok(strongLabels.includes("file:///notes.txt"));
  assert.ok(strongLabels.includes("summarize"));
  const toolsHeading = findElement(container, (node) => node.tagName === "h4" && node.textContent === "Tools");
  const operationsGroup = toolsHeading.parentElement;
  const submitLabels = findElements(operationsGroup, (node) => node.tagName === "button" && node.type === "submit").map((node) => node.textContent);
  assert.deepEqual(
    submitLabels,
    ["Discover", "Invoke", "Read", "Get prompt", "Store credential"],
    "each operation kind must submit with its own verb, in the same order as its group",
  );

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // A stdio (or any privileged_execution) discover is approval-gated, so it resolves through
  // decide(), not through invoke()'s own post-invocation refresh. Approving it must still pick
  // up the newly discovered tools instead of leaving the operator staring at an empty runtime
  // until they navigate away from the extension and back.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  let runStatus = "awaiting_approval";
  let runtimeFetches = 0;
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:fixture", display_name: "Fixture", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({ extension_id: "mcp:fixture", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => {
      runtimeFetches += 1;
      return {
        operations: runtimeFetches > 1
          ? [{ name: "tool:echo", capability_id: "extension-tool1", input_schema: { type: "object", properties: {} }, available: true }]
          : [],
        snapshot: {},
      };
    },
    getExtensionRuns: async () => ({
      runs: [{ run_id: "r1", proposal_id: "p1", extension_id: "mcp:fixture", status: runStatus }],
    }),
    decideAction: async () => { runStatus = "success"; },
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:fixture");
  assert.equal(runtimeFetches, 1, "selecting the extension must fetch runtime once");
  assert.deepEqual(panel.controller.snapshot().runtime.operations, [], "no tools are discovered yet");

  await panel.controller.decide("p1", "approved");

  assert.equal(runtimeFetches, 2, "approving a run for the selected extension must refresh its runtime");
  assert.deepEqual(
    panel.controller.snapshot().runtime.operations.map((op) => op.name),
    ["tool:echo"],
    "the newly discovered tool must reach state without navigating away and back",
  );

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // Source (a raw file/module path) and revision (a concurrency counter) are backend/audit
  // internals; they must sit behind an explicit "Details" disclosure, not the primary facts.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({
      extension_id: "mcp:weather",
      family: "mcp",
      version: "1.0.0",
      source: "data/extensions/mcp/weather.yaml",
      provenance: "data/extensions",
      trust: "operator",
      readiness: "ready",
      availability: "available",
      revision: 3,
      state: "enabled",
    }),
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:weather");

  // Assert by field label (the <dt>), not by scanning rendered text for the raw value: a
  // value like a low revision number can coincidentally appear elsewhere (a version string,
  // an id) and would make a substring check pass or fail for the wrong reason.
  const primaryFacts = findElement(container, (node) => node.tagName === "dl" && node.className === "extensions-facts");
  const primaryLabels = findElements(primaryFacts, (node) => node.tagName === "dt").map((node) => node.textContent);
  assert.ok(!primaryLabels.includes("Source"), "source must not appear in the primary facts");
  assert.ok(!primaryLabels.includes("Revision"), "revision must not appear in the primary facts");

  const details = findElement(container, (node) => node.tagName === "details" && findElement(node, (n) => n.tagName === "summary" && n.textContent === "Details"));
  assert.ok(details, "source and revision must be reachable behind a Details disclosure");
  const detailLabels = findElements(details, (node) => node.tagName === "dt").map((node) => node.textContent);
  assert.ok(detailLabels.includes("Source"));
  assert.ok(detailLabels.includes("Revision"));
  const sourceField = findElement(details, (node) => node.tagName === "dt" && node.textContent === "Source").parentElement;
  assert.equal(findElement(sourceField, (node) => node.tagName === "dd").textContent, "data/extensions/mcp/weather.yaml");
  const revisionField = findElement(details, (node) => node.tagName === "dt" && node.textContent === "Revision").parentElement;
  assert.equal(findElement(revisionField, (node) => node.tagName === "dd").textContent, "3");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // Run polling re-renders this panel roughly once a second while it is open; a scrolled
  // list must not snap back to the top on every poll tick.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionRuns: async () => ({ runs: [] }),
  });
  await panel.open();

  const listColumn = findElement(container, (node) => node.dataset?.scrollKey === "list");
  const detailColumn = findElement(container, (node) => node.dataset?.scrollKey === "detail");
  assert.ok(listColumn, "the catalog list column must carry a stable scroll key");
  assert.ok(detailColumn, "the detail column must carry a stable scroll key");
  listColumn.scrollTop = 240;
  detailColumn.scrollTop = 80;

  await panel.controller.refreshRuns();

  const rerenderedList = findElement(container, (node) => node.dataset?.scrollKey === "list");
  const rerenderedDetail = findElement(container, (node) => node.dataset?.scrollKey === "detail");
  assert.equal(rerenderedList.scrollTop, 240, "the catalog list must keep its scroll position across a run-poll re-render");
  assert.equal(rerenderedDetail.scrollTop, 80, "the detail column must keep its scroll position across a run-poll re-render");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // A focused catalog row must keep focus across a re-render it did not itself invalidate
  // (an unrelated action calling refreshCatalog(), the same call a save/remove/add mutation
  // triggers), rather than silently dropping focus back to nothing.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
    getExtensionErrors: async () => ({ errors: [] }),
  });
  await panel.open();

  const row = findElement(container, (node) => node.dataset?.focusKey === "row:mcp:weather");
  assert.ok(row, "a catalog row must carry a stable focus key");
  row.focus();
  assert.equal(globalThis.document.activeElement, row);

  await panel.controller.refreshCatalog();

  const rerenderedRow = findElement(container, (node) => node.dataset?.focusKey === "row:mcp:weather");
  assert.notEqual(rerenderedRow, row, "the re-render must have produced a fresh element, not reused the old one");
  assert.equal(globalThis.document.activeElement, rerenderedRow, "the same row must regain focus after the re-render");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // Focus restoration is a generic mechanism, but each tagged control is its own rendering
  // branch - a state-transition button, "Show body", and "Remove connection" each need their
  // own proof that the focus key is actually wired, not just that the mechanism works once.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({
      extension_id: "mcp:weather",
      family: "mcp",
      provenance: "data/extensions",
      state: "enabled",
      body_available: true,
    }),
    getExtensionRuntime: async () => ({
      operations: [{ capability_id: "tool:get_forecast", input_schema: {} }],
    }),
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:weather");

  async function assertFocusSurvives(focusKey, describeControl) {
    const before = findElement(container, (node) => node.dataset?.focusKey === focusKey);
    assert.ok(before, `${describeControl} must carry focus key ${focusKey}`);
    before.focus();
    await panel.controller.refreshCatalog();
    const after = findElement(container, (node) => node.dataset?.focusKey === focusKey);
    assert.notEqual(after, before, `${describeControl} re-render must produce a fresh element`);
    assert.equal(globalThis.document.activeElement, after, `${describeControl} must regain focus after the re-render`);
  }

  await assertFocusSurvives("state:mcp:weather:disabled", "the Set disabled button");
  await assertFocusSurvives("show-body:mcp:weather", "the Show body button");
  await assertFocusSurvives("remove-connection:mcp:weather", "the Remove connection button");
  await assertFocusSurvives("add-mcp:submit", "the Add connection submit button");
  await assertFocusSurvives("import-skill:submit", "the Import skill submit button");
  await assertFocusSurvives("credential-submit:mcp:weather", "the Store credential submit button");
  await assertFocusSurvives("operation-submit:mcp:weather:tool:get_forecast", "an operation's submit button");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // A run's id and proposal id are backend correlation identifiers; they must not appear in
  // the run's primary heading, only behind an explicit "Run details" disclosure.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({ extension_id: "mcp:weather", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => ({ operations: [] }),
    getExtensionRuns: async () => ({
      runs: [{
        run_id: "extension-deadbeefcafef00d",
        extension_id: "mcp:weather",
        proposal_id: "prop-123",
        status: "success",
        started_at: "2026-09-08T10:32:00.000Z",
      }],
    }),
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:weather");

  const headings = findElements(container, (node) => node.tagName === "strong");
  const runHeading = headings.find((node) => node.textContent.startsWith("success"));
  assert.ok(runHeading, "the run must render a status-led heading");
  assert.ok(!runHeading.textContent.includes("extension-deadbeefcafef00d"), "the raw run id must not appear in the run heading");

  const runDetails = findElement(container, (node) => node.tagName === "details" && findElement(node, (n) => n.tagName === "summary" && n.textContent === "Run details"));
  assert.ok(runDetails, "the run id and proposal id must be reachable behind a Run details disclosure");
  const runIdField = findElement(runDetails, (node) => node.tagName === "dt" && node.textContent === "Run ID").parentElement;
  assert.equal(findElement(runIdField, (node) => node.tagName === "dd").textContent, "extension-deadbeefcafef00d");
  const proposalField = findElement(runDetails, (node) => node.tagName === "dt" && node.textContent === "Proposal").parentElement;
  assert.equal(findElement(proposalField, (node) => node.tagName === "dd").textContent, "prop-123");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // A "get prompt" result is a list of role-tagged messages, not the tool-shaped result every
  // other operation produces - it must render as readable message text, not the same raw JSON
  // block a tool result falls back to.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({ extension_id: "mcp:weather", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => ({ operations: [] }),
    getExtensionRuns: async () => ({
      runs: [
        {
          // extension_runtime_service.py's _mcp wraps every non-discover result as
          // {content: result, trusted: false} - the SDK's own shape sits one level under
          // result.content, not at the top.
          run_id: "run-prompt", extension_id: "mcp:weather", status: "success", started_at: "2026-09-08T10:32:00.000Z",
          result: { content: { messages: [{ role: "user", content: { type: "text", text: "Summarize today." } }] }, trusted: false },
        },
        {
          run_id: "run-tool", extension_id: "mcp:weather", extension_name: "Weather", operation: "tool:forecast", status: "success", started_at: "2026-09-08T10:33:00.000Z",
          arguments: { city: "London" }, events: [{ type: "tool_completed", detail: "audit only" }],
          result: { content: { content: [{ type: "text", text: "72F and sunny" }] }, trusted: false },
        },
      ],
    }),
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:weather");

  const promptText = findElement(container, (node) => node.tagName === "p" && node.textContent === "user: Summarize today.");
  assert.ok(promptText, "a prompt result must render as role-labeled message text");

  assert.ok(findElement(container, (node) => node.tagName === "pre" && node.textContent === "72F and sunny"));
  assert.ok(findElement(container, (node) => node.tagName === "strong" && node.textContent.startsWith("Weather · forecast · success")));
  assert.ok(findElement(container, (node) => node.tagName === "dd" && node.textContent === "London"));
  assert.ok(findElement(container, (node) => node.tagName === "p" && node.textContent === "Latest event: tool completed"));
  const evidence = findElements(container, (node) => node.tagName === "details");
  assert.ok(evidence.some((node) => findElement(node, (child) => child.tagName === "pre" && child.textContent.includes('"trusted": false'))));

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // A "read resource" result ({contents: [...]}) must render as a content preview - text
  // inline, an image inline - instead of the same raw JSON block a tool result falls back to.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({ extension_id: "mcp:weather", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => ({ operations: [] }),
    getExtensionRuns: async () => ({
      runs: [
        {
          // extension_runtime_service.py's _mcp wraps every non-discover result as
          // {content: result, trusted: false} - the SDK's own shape sits one level under
          // result.content, not at the top.
          run_id: "run-resource-text", extension_id: "mcp:weather", status: "success", started_at: "2026-09-08T10:32:00.000Z",
          result: { content: { contents: [{ uri: "file:///notes.txt", mimeType: "text/plain", text: "It rained today." }] }, trusted: false },
        },
        {
          run_id: "run-resource-image", extension_id: "mcp:weather", status: "success", started_at: "2026-09-08T10:33:00.000Z",
          result: { content: { contents: [{ uri: "file:///radar.png", mimeType: "image/png", blob: "QUJD" }] }, trusted: false },
        },
        {
          run_id: "run-resource-audio", extension_id: "mcp:weather", status: "success", started_at: "2026-09-08T10:34:00.000Z",
          result: { content: { contents: [{ uri: "file:///alert.mp3", mimeType: "audio/mpeg", blob: "QUJD" }] }, trusted: false },
        },
      ],
    }),
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:weather");

  const textPreview = findElement(container, (node) => node.tagName === "pre" && node.textContent === "It rained today.");
  assert.ok(textPreview, "a text resource result must render as a readable preview, not raw JSON");

  const imagePreview = findElement(container, (node) => node.tagName === "img" && node.src === "data:image/png;base64,QUJD");
  assert.ok(imagePreview, "an image resource result must render inline from its base64 blob");

  const audioFallback = findElement(container, (node) => node.tagName === "pre" && node.textContent.includes("audio/mpeg"));
  assert.ok(audioFallback, "a resource kind with no rendering support must still fall back to the raw JSON block");
  assert.ok(audioFallback.textContent.startsWith("{"), "the fallback must be the raw JSON result, not silently dropped");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

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
    scrollTop: 0,
    focus() { this.focused = true; if (globalThis.document) globalThis.document.activeElement = this; },
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
      const dataAttr = /^\[data-([\w-]+)\]$/.exec(selector);
      if (dataAttr) {
        const key = dataAttr[1].replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
        return findElements(this, (node) => node.dataset && Object.prototype.hasOwnProperty.call(node.dataset, key));
      }
      return [];
    },
  };
  Object.defineProperty(element, "childNodes", { get() { return this.children; } });
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
      capability_id: "provider-secret-rotate",
      effect_class: "destructive_action",
      readiness: "ready",
      availability: "available",
      authorization_rule: "requires_approval",
      approval_mode: "same_turn",
      execution_owner: "backend.app.services.llm_provider_profiles.LLMProviderProfileStore",
      unavailable_explanation: "",
      executable: true,
      input_schema: { type: "object", properties: {} },
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
  const runTrigger = buttons.find((node) => node.textContent === "Run");
  assert.ok(runTrigger, "an allow capability must offer a Run control, not a self-approval Propose control");
  const proposeTrigger = buttons.find((node) => node.textContent === "Propose");
  assert.ok(proposeTrigger, "a capability that genuinely requires approval must still offer a Propose control");
  assert.equal(
    buttons.filter((node) => node.textContent === "Run" || node.textContent === "Propose").length,
    2,
    "a turn-boundary capability must not offer a drivable control",
  );
  assert.ok(
    findElement(container, (node) => String(node.textContent).includes("agent-invoke-coder")),
    "a descriptor the registry refused must be explained in the panel",
  );
  assert.ok(
    findElement(container, (node) => String(node.textContent).includes("backend.app.services.search_service.SearchService")),
    "a capability with no proposable executor must name its owner",
  );

  runTrigger.listeners.click();
  const form = findElement(container, (node) => node.className === "actions-propose");
  assert.ok(form, "the Run control must open a form built from the declared input schema");
  const runSubmit = findElement(form, (node) => node.tagName === "button" && node.type === "submit");
  assert.equal(runSubmit.textContent, "Run action", "an allow capability's form must not be labeled as a proposal");
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
  [{ status: "outcome_unknown" }, "degraded"],
]) {
  assert.equal(
    executionActivityState(execution),
    expected,
    "outcome_unknown must render distinctly from an ordinary failure, not fall through to it",
  );
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
assert.equal(
  formatCapabilityApproval({ approval_mode: "same_turn", authorization_rule: "requires_approval" }),
  "requires approval",
);
assert.equal(
  formatCapabilityApproval({ approval_mode: "same_turn", authorization_rule: "allow" }),
  "",
  "an allow capability has no decision to describe, so it must not read as a self-approval ritual",
);

assert.equal(proposeTriggerLabel({ authorization_rule: "requires_approval" }), "Propose");
assert.equal(proposeTriggerLabel({ authorization_rule: "allow" }), "Run");

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
  // "Forget authorization" clears the client's stored token; the panel must refresh oauth
  // status from the backend afterward rather than assume success locally.
  const calls = [];
  let forgotten = false;
  let failClose = false;
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({ extension_id: "mcp:probe", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => ({ operations: [], snapshot: null, connected: failClose || !forgotten }),
    getExtensionRuns: async () => ({ runs: [] }),
    getExtensionOauth: async () => ({ configured: true, authorized: !forgotten }),
    forgetExtensionOauth: async (extensionId) => {
      calls.push(["forget", extensionId]);
      forgotten = true;
      if (failClose) throw new Error("Stored authorization was removed locally, but the connection may still be running.");
    },
  });
  await controller.selectExtension("mcp:probe");
  assert.equal(controller.snapshot().oauthStatus.authorized, true);

  await controller.forgetOauth("mcp:probe");

  assert.deepEqual(calls, [["forget", "mcp:probe"]]);
  assert.equal(
    controller.snapshot().oauthStatus.authorized,
    false,
    "forgetting authorization must refresh oauth status from the backend rather than assume success",
  );
  assert.equal(controller.snapshot().notice, "Stored authorization forgotten.");
  assert.equal(controller.snapshot().runtime.connected, false);
  failClose = true;
  for (let attempt = 0; attempt < 2; attempt += 1) {
    await controller.forgetOauth("mcp:probe");
    assert.equal(controller.snapshot().oauthStatus.authorized, false);
    assert.equal(controller.snapshot().runtime.connected, true);
    assert.match(controller.snapshot().detailError, /removed locally.*may still be running/);
    assert.equal(controller.snapshot().notice, "");
  }
}

{
  // "Disconnect" ends the held session without touching the definition or stored
  // credentials - distinct from "Forget authorization" above and from "Remove
  // connection". The panel must refresh runtime detail from the backend afterward, the
  // same way a completed invocation does, rather than assume anything about the new state.
  const calls = [];
  let health = "ready";
  let connected = true;
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({ extension_id: "mcp:probe", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => ({ operations: [], snapshot: { health }, connected }),
    getExtensionRuns: async () => ({ runs: [] }),
    disconnectExtension: async (extensionId) => {
      calls.push(["disconnect", extensionId]);
      connected = false;
    },
  });
  await controller.selectExtension("mcp:probe");
  assert.equal(controller.snapshot().runtime.snapshot.health, "ready");
  assert.equal(controller.snapshot().runtime.connected, true);

  await controller.disconnect("mcp:probe");

  assert.deepEqual(calls, [["disconnect", "mcp:probe"]]);
  // A probe reproduced the cached discovery snapshot still reading "ready" after
  // Disconnect closed the session - `connected` is the backend's own live signal and
  // must reflect that immediately, distinct from the unrefreshed cached health.
  assert.equal(
    controller.snapshot().runtime.snapshot.health,
    "ready",
    "the cached discovery snapshot is history, not something Disconnect itself rewrites",
  );
  assert.equal(
    controller.snapshot().runtime.connected,
    false,
    "connected must reflect the live session state, not the stale cached health",
  );
  assert.equal(controller.snapshot().notice, "Connection disconnected.");
}

{
  // Disconnect is offered for any MCP connection regardless of current health, unlike
  // "Forget authorization" which only appears once OAuth is configured and authorized.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({ extension_id: "mcp:probe", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => ({ operations: [], snapshot: null }),
    getExtensionRuns: async () => ({ runs: [] }),
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:probe");

  const buttons = findElements(container, (node) => node.tagName === "button").map((node) => node.textContent);
  assert.ok(buttons.includes("Disconnect"), "an MCP connection must always offer Disconnect regardless of its current health");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // A probe reproduced the panel displaying the cached discovery snapshot's "ready"
  // health as if it were current, even after Disconnect had already closed the live
  // session (`connected: false`). The rendered label must reflect the live signal, not
  // the stale cached one.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({ extension_id: "mcp:probe", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => ({ operations: [], snapshot: { health: "ready" }, connected: false }),
    getExtensionRuns: async () => ({ runs: [] }),
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:probe");

  const text = findElements(container, (node) => node.tagName === "p").map((node) => node.textContent);
  assert.ok(
    text.includes("Connection health: not connected"),
    "a disconnected session must not display the stale cached health as current",
  );
  assert.ok(
    !text.some((line) => line === "Connection health: ready"),
    "the cached snapshot's health must not be shown once the live connection is known closed",
  );

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // The "Forget authorization" control only appears once authorized - there is nothing to
  // forget before then, and Connect/Reconnect already cover that state.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({ extension_id: "mcp:probe", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => ({ operations: [], snapshot: null }),
    getExtensionRuns: async () => ({ runs: [] }),
    getExtensionOauth: async () => ({ configured: true, authorized: true }),
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:probe");

  const authorizedButtons = findElements(container, (node) => node.tagName === "button").map((node) => node.textContent);
  assert.ok(authorizedButtons.includes("Forget authorization"), "an authorized OAuth connection must offer to forget its authorization");
  assert.ok(authorizedButtons.includes("Reconnect"), "an authorized connection still offers Reconnect, distinct from forgetting authorization");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({ extension_id: "mcp:probe", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => ({ operations: [], snapshot: null }),
    getExtensionRuns: async () => ({ runs: [] }),
    getExtensionOauth: async () => ({ configured: true, authorized: false }),
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:probe");

  const unauthorizedButtons = findElements(container, (node) => node.tagName === "button").map((node) => node.textContent);
  assert.ok(!unauthorizedButtons.includes("Forget authorization"), "an unauthorized OAuth connection has no stored authorization to forget");
  assert.ok(unauthorizedButtons.includes("Connect"));

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
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

{
  // Operator skills are editable through the governed capability, not a direct write.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async (request) => {
      proposals.push(request);
      return { status: "success" };
    },
  });
  await controller.saveSkill("notes", "---\nname: notes\n---\nbody");
  assert.equal(proposals[0].capabilityId, "extension-skill-write");
  assert.deepEqual(proposals[0].actionArguments, {
    local_id: "notes",
    body: "---\nname: notes\n---\nbody",
  });
  assert.equal(controller.snapshot().notice, "Skill saved.");

  await controller.removeSkill("notes");
  assert.equal(proposals[1].capabilityId, "extension-skill-delete");
  assert.equal(controller.snapshot().selectedExtensionId, "");
}

{
  // A refused save must surface the backend's reason, not claim success.
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async () => ({
      status: "failure",
      execution: { error: "skill declares an authority-bearing field" },
    }),
  });
  await controller.saveSkill("rogue", "---\nname: rogue\n---\nbody");
  const snapshot = controller.snapshot();
  assert.ok(snapshot.detailError.includes("authority-bearing"));
  assert.notEqual(snapshot.notice, "Skill saved.");
}

{
  // A refused delete must surface the backend's reason too, not just a thrown error.
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async () => ({
      status: "failure",
      execution: { error: "skill is referenced by an enabled agent" },
    }),
  });
  await controller.removeSkill("notes");
  const snapshot = controller.snapshot();
  assert.ok(snapshot.detailError.includes("referenced by an enabled agent"));
  assert.notEqual(snapshot.notice, "Skill removed.");
}

{
  // Operator-skill ownership is decided by provenance: these skills carry external trust.
  const panel = readFileSync(new URL("../src/components/extensions-panel.js", import.meta.url), "utf8");
  const editorAt = panel.indexOf('appendText(editor, "Edit skill"');
  assert.ok(editorAt > 0, "the skill editor must exist");
  const guard = panel.slice(panel.lastIndexOf("if (detail.family === \"skill\"", editorAt), editorAt);
  assert.ok(guard.includes("provenance"), "skill editing must gate on provenance");
  assert.ok(!guard.includes('trust === "operator"'), "operator skills do not carry operator trust");
}

{
  // A loaded skill body must actually appear in the Edit skill textarea. The editor renders
  // unconditionally (before any body is loaded) with an empty draft-keyed value, so the
  // capture-then-restore re-render mechanism must not stomp the freshly loaded body back to
  // that pre-load empty value on the very re-render that first populates it.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({
      extensions: [{ extension_id: "skill:notes", display_name: "Notes", family: "skill", trust: "operator", provenance: "data/extensions", version: "1" }],
      families: { skill: 1 },
    }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({ extension_id: "skill:notes", family: "skill", provenance: "data/extensions", body_available: true }),
    getExtensionRuntime: async () => ({ operations: [] }),
    getExtensionBody: async () => ({ extension_id: "skill:notes", body: "the loaded body" }),
  });
  await panel.open();
  await panel.controller.selectExtension("skill:notes");

  function editorTextarea() {
    const heading = findElement(container, (node) => node.tagName === "strong" && node.textContent === "Edit skill");
    return findElement(heading.parentElement, (node) => node.tagName === "textarea");
  }

  const before = editorTextarea();
  assert.equal(before.value, "", "the editor must start empty before a body is loaded");

  await panel.controller.loadBody("skill:notes");

  const after = editorTextarea();
  assert.equal(after.value, "the loaded body", "the editor must show the loaded body, not the stale pre-load draft");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // An operator can add an MCP connection without hand-editing YAML: the same governed
  // capability path as skills, not a direct write.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async (request) => {
      proposals.push(request);
      return { status: "success" };
    },
  });
  await controller.addMcpConnection({ localId: "weather", name: "Weather", url: "https://weather.example.test/mcp" });
  assert.equal(proposals[0].capabilityId, "extension-definition-write");
  assert.deepEqual(proposals[0].actionArguments, {
    family: "mcp",
    local_id: "weather",
    name: "Weather",
    version: "1.0.0",
    definition: { transport: "streamable_http", url: "https://weather.example.test/mcp" },
  });
  assert.equal(controller.snapshot().notice, "MCP connection added.");

  await controller.removeMcpConnection("weather");
  assert.equal(proposals[1].capabilityId, "extension-definition-delete");
  assert.deepEqual(proposals[1].actionArguments, { family: "mcp", local_id: "weather" });
  assert.equal(controller.snapshot().selectedExtensionId, "");
}

{
  // An operator can scope a new connection to specific tools/resources/prompts without
  // sending an empty allowlist, which the backend would treat as "allow nothing" rather
  // than "no restriction".
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.addMcpConnection({
    localId: "weather",
    name: "Weather",
    url: "https://weather.example.test/mcp",
    toolAllowlist: "get_forecast, get_alerts ,",
    resourceAllowlist: "",
    promptAllowlist: "summarize",
  });
  assert.deepEqual(proposals[0].actionArguments.definition, {
    transport: "streamable_http",
    url: "https://weather.example.test/mcp",
    tool_allowlist: ["get_forecast", "get_alerts"],
    prompt_allowlist: ["summarize"],
  }, "a blank allowlist field must be omitted, not sent as an empty array");
}

assert.deepEqual(parseAllowlist("a, b ,  c"), ["a", "b", "c"]);
assert.deepEqual(parseAllowlist(""), []);
assert.deepEqual(parseAllowlist(null), []);
assert.deepEqual(parseAllowlist("a,,b"), ["a", "b"], "an empty item between commas must be dropped");

assert.deepEqual(parseCommandLines("python3\n-m\nscripts.changelog"), ["python3", "-m", "scripts.changelog"]);
assert.deepEqual(parseCommandLines(""), []);
assert.deepEqual(parseCommandLines(null), []);
assert.deepEqual(parseCommandLines("python3\n\n-m\n"), ["python3", "-m"], "a blank line between tokens must be dropped");

{
  // An operator can add a governed local tool without hand-editing YAML, the same governed
  // capability path already used for MCP connections and skills.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.addLocalTool({
    localId: "changelog-writer",
    name: "Changelog writer",
    command: "python3\n-m\nscripts.changelog",
    argvAllowlist: "python3",
    envPassthrough: "",
    workingRoot: "data",
  });
  assert.equal(proposals[0].capabilityId, "extension-definition-write");
  assert.deepEqual(proposals[0].actionArguments, {
    family: "tool",
    local_id: "changelog-writer",
    name: "Changelog writer",
    version: "1.0.0",
    definition: {
      command: ["python3", "-m", "scripts.changelog"],
      process: { subprocess: true, argv_allowlist: ["python3"], env_passthrough: [], working_root: "data" },
    },
  });
  assert.equal(controller.snapshot().notice, "Local tool added.");

  await controller.removeLocalTool("changelog-writer");
  assert.equal(proposals[1].capabilityId, "extension-definition-delete");
  assert.deepEqual(proposals[1].actionArguments, { family: "tool", local_id: "changelog-writer" });
  assert.equal(controller.snapshot().selectedExtensionId, "");
}

{
  // Editing an MCP connection reuses the same write capability Add uses, but must carry the
  // fingerprint the definition was read with, plus its enabled/dependencies/metadata, so a
  // save cannot silently drop fields a hand-authored YAML file declared or overwrite a
  // concurrent change.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather",
      provenance: "data/extensions", definition_available: true, state: "enabled",
    }),
    getExtensionDefinition: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather", name: "Weather", version: "1",
      enabled: true, dependencies: ["search-public-web"], metadata: { owner: "ops" },
      definition: { transport: "streamable_http", url: "https://weather.example.test/mcp" },
      fingerprint: "fingerprint-1",
    }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.selectExtension("mcp:weather");
  await controller.loadDefinition("mcp:weather");
  assert.equal(controller.snapshot().definition.fingerprint, "fingerprint-1");

  await controller.updateMcpConnection({
    localId: "weather", name: "Weather HQ", url: "https://weather.example.test/mcp/v2",
    toolAllowlist: "get_forecast", resourceAllowlist: "", promptAllowlist: "",
  });

  assert.equal(proposals[0].capabilityId, "extension-definition-write");
  assert.deepEqual(proposals[0].actionArguments, {
    family: "mcp", local_id: "weather", name: "Weather HQ", version: "1",
    definition: {
      transport: "streamable_http", url: "https://weather.example.test/mcp/v2",
      tool_allowlist: ["get_forecast"],
    },
    dependencies: ["search-public-web"], metadata: { owner: "ops" }, enabled: true,
    expected_fingerprint: "fingerprint-1",
  });
  assert.equal(controller.snapshot().notice, "MCP connection saved.");
  assert.equal(controller.snapshot().definition, null, "the edit form must close after a successful save");
}

{
  // A stale editor's conflict must surface as the backend's reason, keep the form open for
  // retry, and never claim success.
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather",
      provenance: "data/extensions", definition_available: true, state: "enabled",
    }),
    getExtensionDefinition: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather", name: "Weather", version: "1",
      enabled: true, dependencies: [], metadata: {},
      definition: { transport: "streamable_http", url: "https://weather.example.test/mcp" },
      fingerprint: "stale",
    }),
    proposeAction: async () => ({
      status: "failure",
      execution: { error: "the definition changed since it was read; reload before saving" },
    }),
  });
  await controller.selectExtension("mcp:weather");
  await controller.loadDefinition("mcp:weather");

  await controller.updateMcpConnection({
    localId: "weather", name: "Weather", url: "https://weather.example.test/mcp",
    toolAllowlist: "", resourceAllowlist: "", promptAllowlist: "",
  });

  const snapshot = controller.snapshot();
  assert.ok(snapshot.editConnectionError.includes("changed since it was read"));
  assert.notEqual(snapshot.notice, "MCP connection saved.");
  assert.ok(snapshot.definition, "the edit form must stay open so the operator can reload and retry");
}

{
  // Cancelling an edit closes the form without proposing anything.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather",
      provenance: "data/extensions", definition_available: true, state: "enabled",
    }),
    getExtensionDefinition: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather", name: "Weather", version: "1",
      enabled: true, dependencies: [], metadata: {},
      definition: { transport: "streamable_http", url: "https://weather.example.test/mcp" },
      fingerprint: "fingerprint-1",
    }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.selectExtension("mcp:weather");
  await controller.loadDefinition("mcp:weather");
  assert.ok(controller.snapshot().definition);

  controller.cancelDefinitionEdit();

  assert.equal(controller.snapshot().definition, null);
  assert.equal(proposals.length, 0);
}

{
  // Add and Edit MCP Connection both expose credential_ref and OAuth fields directly, so
  // saving carries whatever the caller passes for them - explicit values set them, and
  // explicitly empty values clear them, the same set-or-delete contract the allowlists already
  // use. The DOM-level tests below prove the Edit form actually prefills these from the loaded
  // definition, which is what makes an untouched field round-trip rather than silently clear.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather",
      provenance: "data/extensions", definition_available: true, state: "enabled",
    }),
    getExtensionDefinition: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather", name: "Weather", version: "1",
      enabled: true, dependencies: [], metadata: {},
      definition: {
        transport: "streamable_http", url: "https://weather.example.test/mcp",
        credential_ref: "weather-api-key",
        oauth: { client_id: "abc", authorization_url: "https://a.test", token_url: "https://t.test" },
      },
      fingerprint: "fingerprint-1",
    }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.selectExtension("mcp:weather");
  await controller.loadDefinition("mcp:weather");

  await controller.updateMcpConnection({
    localId: "weather", name: "Weather HQ", url: "https://weather.example.test/mcp",
    toolAllowlist: "", resourceAllowlist: "", promptAllowlist: "",
    credentialRef: "weather-api-key",
    oauth: { clientId: "abc", authorizationUrl: "https://a.test", tokenUrl: "https://t.test" },
  });

  assert.equal(proposals[0].actionArguments.definition.credential_ref, "weather-api-key");
  assert.deepEqual(proposals[0].actionArguments.definition.oauth, {
    client_id: "abc", authorization_url: "https://a.test", token_url: "https://t.test",
  });
}

{
  // Explicitly clearing credential_ref/oauth on an edit must actually clear them, not leave the
  // base value in place - the same explicit set-or-delete contract the allowlists already use.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather",
      provenance: "data/extensions", definition_available: true, state: "enabled",
    }),
    getExtensionDefinition: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather", name: "Weather", version: "1",
      enabled: true, dependencies: [], metadata: {},
      definition: {
        transport: "streamable_http", url: "https://weather.example.test/mcp",
        credential_ref: "weather-api-key",
        oauth: { client_id: "abc" },
      },
      fingerprint: "fingerprint-1",
    }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.selectExtension("mcp:weather");
  await controller.loadDefinition("mcp:weather");

  await controller.updateMcpConnection({
    localId: "weather", name: "Weather", url: "https://weather.example.test/mcp",
    toolAllowlist: "", resourceAllowlist: "", promptAllowlist: "",
    credentialRef: "", oauth: {},
  });

  assert.equal("credential_ref" in proposals[0].actionArguments.definition, false);
  assert.equal("oauth" in proposals[0].actionArguments.definition, false);
}

{
  // OAuth requires at minimum a client_id; every other field is optional and the backend
  // discovers authorization_url/token_url from the server when both are blank, so the desktop
  // must not require them either. Leaving client_id blank must omit oauth entirely, not send an
  // incomplete block.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.addMcpConnection({
    localId: "weather", name: "Weather", url: "https://weather.example.test/mcp",
    oauth: { clientId: "abc" },
  });
  assert.deepEqual(proposals[0].actionArguments.definition.oauth, { client_id: "abc" });

  await controller.addMcpConnection({
    localId: "weather2", name: "Weather 2", url: "https://weather2.example.test/mcp",
    oauth: { authorizationUrl: "https://a.test", tokenUrl: "https://t.test" },
  });
  assert.equal("oauth" in proposals[1].actionArguments.definition, false, "no client_id means no OAuth configured at all");
}

{
  // Editing a local tool follows the same contract as editing an MCP connection.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({
      extension_id: "tool:changelog-writer", family: "tool", local_id: "changelog-writer",
      provenance: "data/extensions", definition_available: true, state: "enabled",
    }),
    getExtensionDefinition: async () => ({
      extension_id: "tool:changelog-writer", family: "tool", local_id: "changelog-writer",
      name: "Changelog writer", version: "1", enabled: true, dependencies: [], metadata: {},
      definition: {
        command: ["python3", "-m", "scripts.changelog"],
        process: { subprocess: true, argv_allowlist: ["python3"], env_passthrough: [], working_root: "data" },
      },
      fingerprint: "fingerprint-1",
    }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.selectExtension("tool:changelog-writer");
  await controller.loadDefinition("tool:changelog-writer");

  await controller.updateLocalTool({
    localId: "changelog-writer", name: "Changelog writer v2",
    command: "python3\n-m\nscripts.changelog\n--verbose",
    argvAllowlist: "python3", envPassthrough: "", workingRoot: "data",
  });

  assert.equal(proposals[0].capabilityId, "extension-definition-write");
  assert.deepEqual(proposals[0].actionArguments, {
    family: "tool", local_id: "changelog-writer", name: "Changelog writer v2", version: "1",
    definition: {
      command: ["python3", "-m", "scripts.changelog", "--verbose"],
      process: { subprocess: true, argv_allowlist: ["python3"], env_passthrough: [], working_root: "data" },
    },
    dependencies: [], metadata: {}, enabled: true, expected_fingerprint: "fingerprint-1",
  });
  assert.equal(controller.snapshot().notice, "Local tool saved.");
  assert.equal(controller.snapshot().definition, null);
}

{
  // A saved edit must preserve skill_id/script - what makes a tool run a skill's declared
  // script rather than an arbitrary command - rather than rebuilding the definition from only
  // command/process. A command or allowlist edit must not silently detach it from its skill.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({
      extension_id: "tool:changelog-writer", family: "tool", local_id: "changelog-writer",
      provenance: "data/extensions", definition_available: true, state: "enabled",
    }),
    getExtensionDefinition: async () => ({
      extension_id: "tool:changelog-writer", family: "tool", local_id: "changelog-writer",
      name: "Changelog writer", version: "1", enabled: true, dependencies: [], metadata: {},
      definition: {
        command: ["python3", "-m", "scripts.changelog"],
        process: { subprocess: true, argv_allowlist: ["python3"], env_passthrough: [], working_root: "data" },
        skill_id: "changelog-writer-skill",
        script: "run.py",
      },
      fingerprint: "fingerprint-1",
    }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.selectExtension("tool:changelog-writer");
  await controller.loadDefinition("tool:changelog-writer");

  await controller.updateLocalTool({
    localId: "changelog-writer", name: "Changelog writer",
    command: "python3\n-m\nscripts.changelog",
    argvAllowlist: "python3", envPassthrough: "", workingRoot: "data",
  });

  assert.equal(proposals[0].actionArguments.definition.skill_id, "changelog-writer-skill");
  assert.equal(proposals[0].actionArguments.definition.script, "run.py");
}

{
  // A tool always registers as privileged_execution, and boundaries.py refuses a
  // privileged_execution capability whose process boundary declares subprocess: false - so
  // subprocess is not an operator choice offered by the form, and a caller cannot flip it to
  // false either, since addLocalTool never reads a subprocess argument at all.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.addLocalTool({
    localId: "changelog-writer", name: "Changelog writer", command: "python3",
    argvAllowlist: "python3", workingRoot: "data", subprocess: false,
  });
  assert.equal(proposals[0].actionArguments.definition.process.subprocess, true, "subprocess must always be true regardless of caller input");
}

{
  // A malformed tool ID must never reach the backend.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.addLocalTool({ localId: "Not A Valid Id!", name: "Bad", command: "python3", argvAllowlist: "python3", workingRoot: "data" });
  assert.equal(proposals.length, 0, "a malformed tool ID must not reach the backend");
  assert.ok(controller.snapshot().addToolError.includes("Tool ID"));
}

{
  // A refused tool delete must surface the backend's reason, not claim success.
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async () => ({ status: "failure", execution: { error: "tool is referenced by an enabled agent" } }),
  });
  await controller.removeLocalTool("changelog-writer");
  const snapshot = controller.snapshot();
  assert.ok(snapshot.detailError.includes("referenced by an enabled agent"));
  assert.notEqual(snapshot.notice, "Local tool removed.");
}

// extension_runtime_service.py's _mcp wraps every non-discover result as
// {content: result, trusted: false} - the SDK's own shape sits one level under result.content,
// not at the top; both functions below must unwrap it, not read the top level directly.
assert.deepEqual(
  formatPromptMessages({
    content: {
      messages: [
        { role: "user", content: { type: "text", text: "What changed?" } },
        { role: "assistant", content: { type: "text", text: "Nothing yet." } },
      ],
    },
    trusted: false,
  }),
  [{ role: "user", text: "What changed?" }, { role: "assistant", text: "Nothing yet." }],
);
assert.equal(formatPromptMessages({ content: { content: [{ type: "text", text: "tool output" }] }, trusted: false }), null, "a tool-shaped result has no messages array and must not be misread as a prompt result");
assert.equal(formatPromptMessages({ content: { messages: [] }, trusted: false }), null, "an empty messages array is not a usable prompt result");
assert.equal(formatPromptMessages({ content: { messages: [{ role: "user", content: { type: "image", data: "..." } }] }, trusted: false }), null, "non-text prompt content must fall back to raw JSON rather than being silently dropped");
assert.equal(formatPromptMessages({ messages: [{ role: "user", content: { type: "text", text: "unwrapped" } }] }), null, "a result missing the content wrapper must not be misread as unwrapped");
assert.equal(formatPromptMessages(null), null);

assert.deepEqual(
  formatResourceContents({ content: { contents: [{ uri: "file:///notes.txt", mimeType: "text/plain", text: "hello" }] }, trusted: false }),
  [{ uri: "file:///notes.txt", mimeType: "text/plain", kind: "text", text: "hello" }],
);
assert.deepEqual(
  formatResourceContents({ content: { contents: [{ uri: "file:///pixel.png", mimeType: "image/png", blob: "QUJD" }] }, trusted: false }),
  [{ uri: "file:///pixel.png", mimeType: "image/png", kind: "image", dataUrl: "data:image/png;base64,QUJD" }],
);
assert.equal(formatResourceContents({ content: { content: [{ type: "text", text: "tool output" }] }, trusted: false }), null, "a tool-shaped result has no contents array and must not be misread as a resource result");
assert.equal(formatResourceContents({ content: { contents: [] }, trusted: false }), null, "an empty contents array is not a usable resource result");
assert.equal(
  formatResourceContents({ content: { contents: [{ uri: "file:///song.mp3", mimeType: "audio/mpeg", blob: "QUJD" }] }, trusted: false }),
  null,
  "unrenderable binary content (audio, an unrecognized blob type) must fall back to raw JSON rather than being silently dropped",
);
assert.equal(formatResourceContents({ contents: [{ uri: "file:///notes.txt", mimeType: "text/plain", text: "hello" }] }), null, "a result missing the content wrapper must not be misread as unwrapped");
assert.equal(formatResourceContents(null), null);

{
  // A refused connection delete must surface the backend's reason, not claim success.
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async () => ({
      status: "failure",
      execution: { error: "connection is referenced by an enabled agent" },
    }),
  });
  await controller.removeMcpConnection("weather");
  const snapshot = controller.snapshot();
  assert.ok(snapshot.detailError.includes("referenced by an enabled agent"));
  assert.notEqual(snapshot.notice, "MCP connection removed.");
}

{
  // A malformed connection ID must never reach the backend.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.addMcpConnection({ localId: "Not A Valid Id!", name: "Bad", url: "https://x.test/mcp" });
  assert.equal(proposals.length, 0, "an invalid connection id must not be proposed");
  assert.match(controller.snapshot().addConnectionError, /Connection ID/);
}

{
  // A refused add must surface the backend's reason, not claim success.
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async () => ({
      status: "failure",
      execution: { error: "MCP definition has unknown fields: bogus" },
    }),
  });
  await controller.addMcpConnection({ localId: "bad", name: "Bad", url: "https://x.test/mcp" });
  const snapshot = controller.snapshot();
  assert.ok(snapshot.addConnectionError.includes("unknown fields"));
  assert.notEqual(snapshot.notice, "MCP connection added.");
}

{
  // MCP connection ownership is decided by provenance, the same rule as skills.
  const panel = readFileSync(new URL("../src/components/extensions-panel.js", import.meta.url), "utf8");
  const removeAt = panel.indexOf('remove.textContent = "Remove connection"');
  assert.ok(removeAt > 0, "the remove-connection control must exist");
  const guard = panel.slice(panel.lastIndexOf("if (isOperatorOwnedProvenance(detail))", removeAt), removeAt);
  assert.ok(guard.includes("isOperatorOwnedProvenance"), "connection removal must gate on provenance");
}

{
  // Local tool ownership is decided by provenance, the same rule as MCP connections and skills.
  const panel = readFileSync(new URL("../src/components/extensions-panel.js", import.meta.url), "utf8");
  const removeAt = panel.indexOf('remove.textContent = "Remove tool"');
  assert.ok(removeAt > 0, "the remove-tool control must exist");
  const guard = panel.slice(panel.lastIndexOf('if (detail.family === "tool"', removeAt), removeAt);
  assert.ok(guard.includes("isOperatorOwnedProvenance"), "tool removal must gate on provenance");
}

{
  // The Add MCP Connection control must render as a real, human-labeled form, not raw
  // JSON, and its submit must reach the governed capability with typed arguments.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const proposals = [];
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionErrors: async () => ({ errors: [] }),
    proposeAction: async (request) => {
      proposals.push(request);
      return { status: "success" };
    },
  });
  await panel.open();

  const form = findElement(container, (node) => node.className === "extensions-add-connection");
  assert.ok(form, "the Add MCP connection form must render");
  const name = findElement(form, (node) => node.placeholder === "Display name");
  const localId = findElement(form, (node) => node.placeholder === "Connection ID (e.g. weather)");
  const url = findElement(form, (node) => node.placeholder === "https://server.example/mcp");
  const toolAllowlist = findElement(form, (node) => node.placeholder === "Allowed tools (comma-separated, optional)");
  const resourceAllowlist = findElement(form, (node) => node.placeholder === "Allowed resources (comma-separated, optional)");
  const promptAllowlist = findElement(form, (node) => node.placeholder === "Allowed prompts (comma-separated, optional)");
  assert.equal(name.placeholder, "Display name");
  assert.equal(localId.placeholder, "Connection ID (e.g. weather)");
  assert.equal(url.placeholder, "https://server.example/mcp");
  assert.equal(toolAllowlist.placeholder, "Allowed tools (comma-separated, optional)");
  assert.equal(resourceAllowlist.placeholder, "Allowed resources (comma-separated, optional)");
  assert.equal(promptAllowlist.placeholder, "Allowed prompts (comma-separated, optional)");
  const submit = findElement(form, (node) => node.tagName === "button" && node.textContent === "Add connection");
  assert.ok(submit, "the form must offer an Add connection control");

  name.value = "Weather";
  localId.value = "weather";
  url.value = "https://weather.example.test/mcp";
  toolAllowlist.value = "get_forecast";
  await form.listeners.submit({ preventDefault() {} });

  assert.equal(proposals[0]?.capabilityId, "extension-definition-write");
  assert.deepEqual(proposals[0]?.actionArguments, {
    family: "mcp",
    local_id: "weather",
    name: "Weather",
    version: "1.0.0",
    definition: {
      transport: "streamable_http",
      url: "https://weather.example.test/mcp",
      tool_allowlist: ["get_forecast"],
    },
  });

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // Edit MCP Connection: clicking "Edit connection" loads the stored definition and renders a
  // form prefilled from it (not the empty Add form), and submitting reaches the governed
  // capability carrying the fingerprint the definition was read with.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const proposals = [];
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", provenance: "data/extensions", version: "1" }],
      families: { mcp: 1 },
    }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather",
      provenance: "data/extensions", definition_available: true, state: "enabled",
    }),
    getExtensionRuntime: async () => ({ operations: [] }),
    getExtensionDefinition: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather", name: "Weather", version: "1",
      enabled: true, dependencies: [], metadata: {},
      definition: { transport: "streamable_http", url: "https://weather.example.test/mcp" },
      fingerprint: "fingerprint-1",
    }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:weather");

  const editButton = findElement(container, (node) => node.tagName === "button" && node.textContent === "Edit connection");
  assert.ok(editButton, "an operator-owned connection with a readable definition must offer Edit connection");
  await editButton.listeners.click();

  const editForm = findElement(container, (node) => node.className === "extensions-edit-connection");
  assert.ok(editForm, "editing must render a distinct form, not reuse the empty Add form");
  const nameField = findElement(editForm, (node) => node.placeholder === "Display name");
  const urlField = findElement(editForm, (node) => node.placeholder === "https://server.example/mcp");
  assert.equal(nameField.value, "Weather", "the form must be prefilled from the loaded definition");
  assert.equal(urlField.value, "https://weather.example.test/mcp");

  urlField.value = "https://weather.example.test/mcp/v2";
  await editForm.listeners.submit({ preventDefault() {} });

  assert.equal(proposals[0]?.capabilityId, "extension-definition-write");
  assert.equal(proposals[0]?.actionArguments.expected_fingerprint, "fingerprint-1");
  assert.equal(proposals[0]?.actionArguments.definition.url, "https://weather.example.test/mcp/v2");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // Edit MCP Connection must prefill credential reference and OAuth fields from the loaded
  // definition, and an unrelated field edit (display name) must leave an untouched
  // credential/OAuth configuration intact - the round trip that makes these fields safe to
  // expose without an operator accidentally erasing authentication on every save.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const proposals = [];
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", provenance: "data/extensions", version: "1" }],
      families: { mcp: 1 },
    }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather",
      provenance: "data/extensions", definition_available: true, state: "enabled",
    }),
    getExtensionRuntime: async () => ({ operations: [] }),
    getExtensionDefinition: async () => ({
      extension_id: "mcp:weather", family: "mcp", local_id: "weather", name: "Weather", version: "1",
      enabled: true, dependencies: [], metadata: {},
      definition: {
        transport: "streamable_http", url: "https://weather.example.test/mcp",
        credential_ref: "weather-api-key",
        oauth: { client_id: "abc", authorization_url: "https://a.test", token_url: "https://t.test", scopes: ["read"] },
      },
      fingerprint: "fingerprint-1",
    }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:weather");
  const editButton = findElement(container, (node) => node.tagName === "button" && node.textContent === "Edit connection");
  await editButton.listeners.click();

  const editForm = findElement(container, (node) => node.className === "extensions-edit-connection");
  const credentialRefField = findElement(editForm, (node) => node.placeholder?.startsWith("Credential reference"));
  const oauthClientIdField = findElement(editForm, (node) => node.placeholder === "OAuth client ID (optional)");
  const oauthScopesField = findElement(editForm, (node) => node.placeholder === "OAuth scopes (comma-separated, optional)");
  assert.equal(credentialRefField.value, "weather-api-key", "credential reference must be prefilled from the loaded definition");
  assert.equal(oauthClientIdField.value, "abc", "OAuth client ID must be prefilled from the loaded definition");
  assert.equal(oauthScopesField.value, "read", "OAuth scopes must be prefilled from the loaded definition");

  const nameField = findElement(editForm, (node) => node.placeholder === "Display name");
  nameField.value = "Weather HQ";
  await editForm.listeners.submit({ preventDefault() {} });

  assert.equal(proposals[0].actionArguments.definition.credential_ref, "weather-api-key", "an unrelated edit must not clear credential_ref");
  assert.deepEqual(proposals[0].actionArguments.definition.oauth, {
    client_id: "abc", authorization_url: "https://a.test", token_url: "https://t.test", scopes: ["read"],
  }, "an unrelated edit must not clear the OAuth configuration");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // Add MCP Connection must also expose credential reference and OAuth fields, so a new
  // connection can be fully configured without a follow-up edit.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const proposals = [];
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionErrors: async () => ({ errors: [] }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await panel.open();

  const form = findElement(container, (node) => node.className === "extensions-add-connection");
  const credentialRefField = findElement(form, (node) => node.placeholder?.startsWith("Credential reference"));
  const oauthClientIdField = findElement(form, (node) => node.placeholder === "OAuth client ID (optional)");
  assert.ok(credentialRefField, "the Add form must offer a credential reference field");
  assert.ok(oauthClientIdField, "the Add form must offer an OAuth client ID field");

  const [name, localId, url] = findElements(form, (node) => node.tagName === "input");
  name.value = "Weather";
  localId.value = "weather";
  url.value = "https://weather.example.test/mcp";
  credentialRefField.value = "weather-api-key";
  oauthClientIdField.value = "abc";
  await form.listeners.submit({ preventDefault() {} });

  assert.equal(proposals[0]?.actionArguments.definition.credential_ref, "weather-api-key");
  assert.deepEqual(proposals[0]?.actionArguments.definition.oauth, { client_id: "abc" });

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // Add MCP Connection for a stdio transport must build the same command/process shape Add
  // Local Tool already establishes, with a credential reference automatically folded into
  // env_passthrough - ProcessBoundary.scrub_environment is an allowlist, so a credential the
  // connection does not pass through would otherwise start the server unauthenticated.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.addMcpConnection({
    localId: "local-tool-server", name: "Local tool server", transport: "stdio",
    command: "python3\n-m\nmymcp.server",
    argvAllowlist: "python3", envPassthrough: "", workingRoot: "data",
    credentialRef: "MY_API_KEY",
  });

  assert.equal(proposals[0].capabilityId, "extension-definition-write");
  assert.deepEqual(proposals[0].actionArguments, {
    family: "mcp", local_id: "local-tool-server", name: "Local tool server", version: "1.0.0",
    definition: {
      transport: "stdio",
      command: ["python3", "-m", "mymcp.server"],
      credential_ref: "MY_API_KEY",
      process: {
        subprocess: true, argv_allowlist: ["python3"],
        env_passthrough: ["MY_API_KEY"], working_root: "data",
      },
    },
  });
}

{
  // Editing a stdio connection must preserve its transport (not switch it), and an edit that
  // changes the command must not silently drop the allowlists or credential reference already
  // configured - the same base-preserving contract streamable_http editing already has.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionDetail: async () => ({
      extension_id: "mcp:local-tool-server", family: "mcp", local_id: "local-tool-server",
      provenance: "data/extensions", definition_available: true, state: "enabled",
    }),
    getExtensionDefinition: async () => ({
      extension_id: "mcp:local-tool-server", family: "mcp", local_id: "local-tool-server",
      name: "Local tool server", version: "1", enabled: true, dependencies: [], metadata: {},
      definition: {
        transport: "stdio",
        command: ["python3", "-m", "mymcp.server"],
        credential_ref: "MY_API_KEY",
        tool_allowlist: ["get_forecast"],
        process: {
          subprocess: true, argv_allowlist: ["python3"],
          env_passthrough: ["MY_API_KEY"], working_root: "data",
        },
      },
      fingerprint: "fingerprint-1",
    }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.selectExtension("mcp:local-tool-server");
  await controller.loadDefinition("mcp:local-tool-server");

  await controller.updateMcpConnection({
    localId: "local-tool-server", name: "Local tool server",
    command: "python3\n-m\nmymcp.server\n--verbose",
    argvAllowlist: "python3", envPassthrough: "MY_API_KEY", workingRoot: "data",
    toolAllowlist: "get_forecast", resourceAllowlist: "", promptAllowlist: "",
    credentialRef: "MY_API_KEY",
  });

  assert.equal(proposals[0].actionArguments.definition.transport, "stdio", "transport must not change on an edit");
  assert.deepEqual(proposals[0].actionArguments.definition.command, ["python3", "-m", "mymcp.server", "--verbose"]);
  assert.deepEqual(proposals[0].actionArguments.definition.tool_allowlist, ["get_forecast"], "an untouched allowlist must survive the edit");
  assert.equal(proposals[0].actionArguments.definition.credential_ref, "MY_API_KEY");
  assert.equal(proposals[0].actionArguments.expected_fingerprint, "fingerprint-1");
}

{
  // The Add MCP Connection form's transport select must toggle between the streamable_http and
  // stdio field sets, and submitting with stdio selected must reach the governed capability
  // with the argv-shaped definition instead of the URL-shaped one.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const proposals = [];
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionErrors: async () => ({ errors: [] }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await panel.open();

  function currentForm() {
    return findElement(container, (node) => node.className === "extensions-add-connection");
  }
  function urlField(form) {
    return findElement(form, (node) => node.placeholder === "https://server.example/mcp");
  }
  function commandField(form) {
    return findElement(form, (node) => node.tagName === "textarea");
  }

  let form = currentForm();
  let url = urlField(form);
  let command = commandField(form);
  assert.equal(url.parentElement.hidden, false, "streamable_http fields must be visible by default");
  assert.equal(url.required, true, "url must be required by default");
  assert.equal(command.parentElement.hidden, true, "stdio fields must be hidden by default");
  assert.equal(command.required, false, "command must not be required by default");

  const transport = findElement(form, (node) => node.tagName === "select" && findElement(node, (opt) => opt.value === "stdio"));
  assert.ok(transport, "the Add form must offer a transport select with a stdio option");
  transport.value = "stdio";
  transport.listeners.change();

  // Selecting stdio goes through real controller state (setAddConnectionTransport), not a
  // DOM-only toggle, so the whole panel re-renders here - stale references to the pre-change
  // form must not be reused.
  form = currentForm();
  url = urlField(form);
  command = commandField(form);
  const argvAllowlist = findElement(form, (node) => node.placeholder === "Allowed executable (comma-separated, e.g. python3)");
  assert.equal(url.parentElement.hidden, true, "streamable_http fields must hide once stdio is selected");
  assert.equal(url.required, false, "url must not be required once stdio is selected");
  assert.equal(command.parentElement.hidden, false, "stdio fields must become visible once stdio is selected");
  assert.equal(command.required, true, "command must be required once stdio is selected");

  // A re-render this form did not cause - the exact class of bug reported: a poll tick or an
  // unrelated pending/error state emit rebuilds the form from scratch, and the transport
  // <select>'s value is restored by the generic draft mechanism without dispatching a change
  // event, so anything relying on that event to toggle visibility would revert to the
  // streamable_http defaults here even though "stdio" is still the selected transport.
  await panel.controller.refreshCatalog();
  form = currentForm();
  url = urlField(form);
  command = commandField(form);
  const transportAfterRefresh = findElement(form, (node) => node.tagName === "select" && findElement(node, (opt) => opt.value === "stdio"));
  assert.equal(transportAfterRefresh.value, "stdio", "the transport selection must survive an unrelated re-render");
  assert.equal(url.parentElement.hidden, true, "streamable_http fields must stay hidden after an unrelated re-render");
  assert.equal(url.required, false, "url must stay non-required after an unrelated re-render");
  assert.equal(command.parentElement.hidden, false, "stdio fields must stay visible after an unrelated re-render");
  assert.equal(command.required, true, "command must stay required after an unrelated re-render");

  const name = findElement(form, (node) => node.placeholder === "Display name");
  const localId = findElement(form, (node) => node.placeholder === "Connection ID (e.g. weather)");
  const argvAllowlistFinal = findElement(form, (node) => node.placeholder === "Allowed executable (comma-separated, e.g. python3)");
  name.value = "Local tool server";
  localId.value = "local-tool-server";
  command.value = "python3\n-m\nmymcp.server";
  argvAllowlistFinal.value = "python3";
  await form.listeners.submit({ preventDefault() {} });

  assert.equal(proposals[0]?.actionArguments.definition.transport, "stdio");
  assert.deepEqual(proposals[0]?.actionArguments.definition.command, ["python3", "-m", "mymcp.server"]);
  assert.equal(proposals[0]?.actionArguments.definition.url, undefined, "a stdio connection must not carry a url");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // Edit MCP Connection for a stdio connection must render the stdio field set (command, argv
  // allowlist, environment passthrough, working root), not the streamable_http url field.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const proposals = [];
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:local-tool-server", display_name: "Local tool server", family: "mcp", trust: "operator", provenance: "data/extensions", version: "1" }],
      families: { mcp: 1 },
    }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({
      extension_id: "mcp:local-tool-server", family: "mcp", local_id: "local-tool-server",
      provenance: "data/extensions", definition_available: true, state: "enabled",
    }),
    getExtensionRuntime: async () => ({ operations: [] }),
    getExtensionDefinition: async () => ({
      extension_id: "mcp:local-tool-server", family: "mcp", local_id: "local-tool-server",
      name: "Local tool server", version: "1", enabled: true, dependencies: [], metadata: {},
      definition: {
        transport: "stdio",
        command: ["python3", "-m", "mymcp.server"],
        credential_ref: "MY_API_KEY",
        process: {
          subprocess: true, argv_allowlist: ["python3"],
          env_passthrough: ["MY_API_KEY"], working_root: "data",
        },
      },
      fingerprint: "fingerprint-1",
    }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:local-tool-server");

  const editButton = findElement(container, (node) => node.tagName === "button" && node.textContent === "Edit connection");
  await editButton.listeners.click();

  const editForm = findElement(container, (node) => node.className === "extensions-edit-connection");
  assert.ok(editForm, "editing a stdio connection must render the edit form, not a fallback notice");
  const commandField = findElement(editForm, (node) => node.tagName === "textarea");
  const urlField = findElement(editForm, (node) => node.placeholder === "https://server.example/mcp");
  const oauthField = findElement(editForm, (node) => node.placeholder === "OAuth client ID (optional)");
  assert.equal(commandField.value, "python3\n-m\nmymcp.server", "the form must be prefilled from the loaded stdio definition");
  assert.equal(urlField, null, "a stdio connection's edit form must not offer a url field");
  assert.equal(oauthField, null, "a stdio connection's edit form must not offer OAuth fields");

  commandField.value = "python3\n-m\nmymcp.server\n--verbose";
  await editForm.listeners.submit({ preventDefault() {} });

  assert.equal(proposals[0]?.actionArguments.definition.transport, "stdio");
  assert.deepEqual(proposals[0]?.actionArguments.definition.command, ["python3", "-m", "mymcp.server", "--verbose"]);
  assert.equal(proposals[0]?.actionArguments.definition.credential_ref, "MY_API_KEY", "an unrelated field edit must not clear credential_ref");

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // The Add Local Tool control must render as a real, human-labeled form, not raw JSON,
  // and its submit must reach the governed capability with typed, argv-shaped arguments.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const proposals = [];
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionErrors: async () => ({ errors: [] }),
    proposeAction: async (request) => {
      proposals.push(request);
      return { status: "success" };
    },
  });
  await panel.open();

  const form = findElement(container, (node) => node.className === "extensions-add-tool");
  assert.ok(form, "the Add Local Tool form must render");
  const name = findElement(form, (node) => node.placeholder === "Display name");
  const localId = findElement(form, (node) => node.placeholder === "Tool ID (e.g. changelog-writer)");
  const command = findElement(form, (node) => node.tagName === "textarea");
  const argvAllowlist = findElement(form, (node) => node.placeholder === "Allowed executable (comma-separated, e.g. python3)");
  const workingRoot = findElement(form, (node) => node.tagName === "select");
  assert.ok(name && localId && command && argvAllowlist && workingRoot, "the form must expose command, argv allowlist, and working root controls");
  const submit = findElement(form, (node) => node.tagName === "button" && node.textContent === "Add tool");
  assert.ok(submit, "the form must offer an Add tool control");

  name.value = "Changelog writer";
  localId.value = "changelog-writer";
  command.value = "python3\n-m\nscripts.changelog";
  argvAllowlist.value = "python3";
  workingRoot.value = "data";
  await form.listeners.submit({ preventDefault() {} });

  assert.equal(proposals[0]?.capabilityId, "extension-definition-write");
  assert.deepEqual(proposals[0]?.actionArguments, {
    family: "tool",
    local_id: "changelog-writer",
    name: "Changelog writer",
    version: "1.0.0",
    definition: {
      command: ["python3", "-m", "scripts.changelog"],
      process: { subprocess: true, argv_allowlist: ["python3"], env_passthrough: [], working_root: "data" },
    },
  });

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // Edit Local Tool: clicking "Edit tool" loads the stored definition and renders a form
  // prefilled from it, and submitting reaches the governed capability with the fingerprint.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const proposals = [];
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({
      extensions: [{ extension_id: "tool:changelog-writer", display_name: "Changelog writer", family: "tool", trust: "operator", provenance: "data/extensions", version: "1" }],
      families: { tool: 1 },
    }),
    getExtensionErrors: async () => ({ errors: [] }),
    getExtensionDetail: async () => ({
      extension_id: "tool:changelog-writer", family: "tool", local_id: "changelog-writer",
      provenance: "data/extensions", definition_available: true, state: "enabled",
    }),
    getExtensionRuntime: async () => ({ operations: [] }),
    getExtensionDefinition: async () => ({
      extension_id: "tool:changelog-writer", family: "tool", local_id: "changelog-writer",
      name: "Changelog writer", version: "1", enabled: true, dependencies: [], metadata: {},
      definition: {
        command: ["python3", "-m", "scripts.changelog"],
        process: { subprocess: true, argv_allowlist: ["python3"], env_passthrough: [], working_root: "data" },
      },
      fingerprint: "fingerprint-1",
    }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await panel.open();
  await panel.controller.selectExtension("tool:changelog-writer");

  const editButton = findElement(container, (node) => node.tagName === "button" && node.textContent === "Edit tool");
  assert.ok(editButton, "an operator-owned tool with a readable definition must offer Edit tool");
  await editButton.listeners.click();

  const editForm = findElement(container, (node) => node.className === "extensions-edit-tool");
  assert.ok(editForm, "editing must render a distinct form, not reuse the empty Add form");
  const commandField = findElement(editForm, (node) => node.tagName === "textarea");
  assert.equal(commandField.value, "python3\n-m\nscripts.changelog", "the form must be prefilled from the loaded definition");

  commandField.value = "python3\n-m\nscripts.changelog\n--verbose";
  await editForm.listeners.submit({ preventDefault() {} });

  assert.equal(proposals[0]?.capabilityId, "extension-definition-write");
  assert.equal(proposals[0]?.actionArguments.expected_fingerprint, "fingerprint-1");
  assert.deepEqual(proposals[0]?.actionArguments.definition.command, ["python3", "-m", "scripts.changelog", "--verbose"]);

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // An operator can import a brand-new skill without hand-editing YAML, distinct from
  // saveSkill's edit-existing path so its error/notice do not land in the wrong place.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async (request) => {
      proposals.push(request);
      return { status: "success" };
    },
  });
  await controller.importSkill("changelog-writer", "---\nname: Changelog Writer\n---\nbody");
  assert.equal(proposals[0].capabilityId, "extension-skill-write");
  assert.deepEqual(proposals[0].actionArguments, {
    local_id: "changelog-writer",
    body: "---\nname: Changelog Writer\n---\nbody",
  });
  assert.equal(controller.snapshot().notice, "Skill imported.");
}

{
  // A malformed skill ID must never reach the backend.
  const proposals = [];
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
  });
  await controller.importSkill("Not A Valid Id!", "---\nname: Bad\n---\nbody");
  assert.equal(proposals.length, 0, "an invalid skill id must not be proposed");
  assert.match(controller.snapshot().importSkillError, /Skill ID/);
}

{
  // A refused import must surface the backend's reason, not claim success.
  const controller = createExtensionsPanelController({
    getExtensions: async () => ({ extensions: [], families: {} }),
    proposeAction: async () => ({
      status: "failure",
      execution: { error: "skill declares an authority-bearing field" },
    }),
  });
  await controller.importSkill("rogue", "---\nname: rogue\n---\nbody");
  const snapshot = controller.snapshot();
  assert.ok(snapshot.importSkillError.includes("authority-bearing"));
  assert.notEqual(snapshot.notice, "Skill imported.");
}

{
  // The Import Skill control must render as a real form, not raw JSON, and its submit
  // must reach the governed capability with typed arguments.
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const proposals = [];
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionErrors: async () => ({ errors: [] }),
    proposeAction: async (request) => {
      proposals.push(request);
      return { status: "success" };
    },
  });
  await panel.open();

  const form = findElement(container, (node) => node.className === "extensions-import-skill");
  assert.ok(form, "the Import skill form must render");
  const localId = findElement(form, (node) => node.tagName === "input");
  const body = findElement(form, (node) => node.tagName === "textarea");
  assert.equal(localId.placeholder, "Skill ID (e.g. changelog-writer)");
  assert.ok(body.placeholder.includes("name:"));
  const submit = findElement(form, (node) => node.tagName === "button" && node.textContent === "Import skill");
  assert.ok(submit, "the form must offer an Import skill control");

  localId.value = "changelog-writer";
  body.value = "---\nname: Changelog Writer\n---\nbody";
  await form.listeners.submit({ preventDefault() {} });

  assert.equal(proposals[0]?.capabilityId, "extension-skill-write");
  assert.deepEqual(proposals[0]?.actionArguments, {
    local_id: "changelog-writer",
    body: "---\nname: Changelog Writer\n---\nbody",
  });

  panel.close();
  globalThis.document = previousDocument;
  globalThis.window = previousWindow;
}

{
  // main.js must wire every handler extensions-panel.js actually calls. getExtensionDefinition
  // was missing this way once: loadDefinition() returned immediately because
  // handlers.getExtensionDefinition was undefined in the real mounted app, yet every isolated
  // controller/DOM test in this file passed anyway because each one supplies its own mock
  // handlers directly - only the real wiring in main.js could go silently stale like this.
  const panelSource = readFileSync(new URL("../src/components/extensions-panel.js", import.meta.url), "utf8");
  const mainSource = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");
  const usedHandlers = new Set([...panelSource.matchAll(/handlers\.([a-zA-Z]+)/g)].map((match) => match[1]));
  assert.ok(usedHandlers.size > 10, "sanity check: the extraction must find the panel's known handler calls");
  const callStart = mainSource.indexOf("createExtensionsPanel(");
  assert.ok(callStart > 0, "main.js must mount the extensions panel");
  const callEnd = mainSource.indexOf("\n);", callStart);
  const wired = mainSource.slice(callStart, callEnd);
  const missing = [...usedHandlers].filter((name) => !wired.includes(`${name}:`));
  assert.deepEqual(missing, [], `main.js must wire every handler extensions-panel.js calls; missing: ${missing.join(", ")}`);
}
