import { test } from "node:test";
import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { createExtensionsPanel, createExtensionsPanelController, extensionActivityState, extensionStateEnabled, formatExtensionOrigin, formatPromptMessages, formatResourceContents, formatRunStarted, operationDisplayName, operationKind, operationShortLabel, operationSubmitLabel, parseAllowlist, parseCommandLines, requestedCapabilities, extensionLocalIdValid, extensionRunTitle, formatToolResult } from "../src/components/extensions-panel.js";
import { main, apiClient, memoryPanel, actionsPanel, extensionsPanel, agentsPanel, backend, createElement, deferred, findElement, findElements } from "./support.mjs";

// Mounts the extensions panel on the test DOM with empty-catalog defaults; done() closes it and
// restores the globals it replaced.
function mountExtensionsPanel(handlers) {
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  const container = createElement("div");
  const panel = createExtensionsPanel(container, {
    getExtensions: async () => ({ extensions: [], families: {} }),
    getExtensionErrors: async () => ({ errors: [] }),
    ...handlers,
  });
  return {
    container,
    panel,
    done() {
      panel.close();
      globalThis.document = previousDocument;
      globalThis.window = previousWindow;
    },
  };
}

test("the extension controller must route invoke, answer, and decide to their handlers", async () => {
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
});

test("Invoking an operation such as MCP \"discover\" changes the extension's own runtime detail (health,...", async () => {
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
});

test("An approval-gated invocation has not run yet, so there is nothing new to refresh", async () => {
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
});

test("A timeout or cancellation can leave the backend unable to tell whether a call already ran on the far side...", async () => {
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
});

test("operation labels must name discover, invoke, read, and get prompt", async () => {
  assert.equal(operationDisplayName({ name: "discover" }), "Discover tools and resources");
  assert.equal(operationDisplayName({ name: "tool:get_forecast" }), "tool:get_forecast");
  assert.equal(operationSubmitLabel({ name: "discover" }), "Discover");
  assert.equal(operationSubmitLabel({ name: "tool:get_forecast" }), "Invoke");
  assert.equal(operationSubmitLabel({ name: "resource:file:///notes.txt" }), "Read", "a resource has no arguments to fill in, so it is read, not invoked");
  assert.equal(operationSubmitLabel({ name: "prompt:summarize" }), "Get prompt");
  assert.equal(operationSubmitLabel({ name: "run" }), "Invoke", "a non-MCP operation keeps the generic verb");
});

test("extension run start times must format for display", async () => {
  assert.equal(formatRunStarted(null), "—");
  assert.equal(formatRunStarted("not a date"), "not a date", "an unparseable timestamp must still display something rather than \"Invalid Date\"");
  assert.equal(
    formatRunStarted("2026-09-08T10:32:00.000Z"),
    new Date("2026-09-08T10:32:00.000Z").toLocaleTimeString(),
  );
});

test("a non-MCP operation must not be miscategorized", async () => {
  assert.equal(operationKind({ name: "discover" }), "discover");
  assert.equal(operationKind({ name: "tool:get_forecast" }), "tool");
  assert.equal(operationKind({ name: "resource:file:///notes.txt" }), "resource");
  assert.equal(operationKind({ name: "prompt:summarize" }), "prompt");
  assert.equal(operationKind({ name: "run" }), "other", "a non-MCP operation must not be miscategorized");
  assert.equal(operationKind({ name: "prompt" }), "other", "an ACP operation literally named prompt must not collide with the MCP prompt group");
});

test("only the first colon marks the group prefix", async () => {
  assert.equal(operationShortLabel({ name: "tool:get_forecast" }), "get_forecast");
  assert.equal(operationShortLabel({ name: "resource:file:///notes.txt" }), "file:///notes.txt", "only the first colon marks the group prefix");
  assert.equal(operationShortLabel({ name: "prompt:summarize" }), "summarize");
  assert.equal(operationShortLabel({ name: "run" }), "run", "a non-grouped operation keeps its plain display name");
});

test("Discovered tools, resources, and prompts must render as separate labeled groups, not one flat \"Operations\"...", async () => {
  // Discovered tools, resources, and prompts must render as separate labeled groups, not
  // one flat "Operations" list mixing internal capability shapes together.
  const { container, panel, done } = mountExtensionsPanel({
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
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

  done();
});

test("A stdio (or any privileged_execution) discover is approval-gated, so it resolves through decide(), not...", async () => {
  // A stdio (or any privileged_execution) discover is approval-gated, so it resolves through
  // decide(), not through invoke()'s own post-invocation refresh. Approving it must still pick
  // up the newly discovered tools instead of leaving the operator staring at an empty runtime
  // until they navigate away from the extension and back.
  let runStatus = "awaiting_approval";
  let runtimeFetches = 0;
  const { container, panel, done } = mountExtensionsPanel({
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:fixture", display_name: "Fixture", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
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

  done();
});

test("Source (a raw file/module path) and revision (a concurrency counter) are backend/audit internals; they...", async () => {
  // Source (a raw file/module path) and revision (a concurrency counter) are backend/audit
  // internals; they must sit behind an explicit "Details" disclosure, not the primary facts.
  const { container, panel, done } = mountExtensionsPanel({
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

  done();
});

test("Run polling re-renders this panel roughly once a second while it is open; a scrolled list must not snap...", async () => {
  // Run polling re-renders this panel roughly once a second while it is open; a scrolled
  // list must not snap back to the top on every poll tick.
  const { container, panel, done } = mountExtensionsPanel({
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

  done();
});

test("A focused catalog row must keep focus across a re-render it did not itself invalidate (an unrelated action...", async () => {
  // A focused catalog row must keep focus across a re-render it did not itself invalidate
  // (an unrelated action calling refreshCatalog(), the same call a save/remove/add mutation
  // triggers), rather than silently dropping focus back to nothing.
  const { container, panel, done } = mountExtensionsPanel({
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
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

  done();
});

test("Focus restoration is a generic mechanism, but each tagged control is its own rendering branch - a...", async () => {
  // Focus restoration is a generic mechanism, but each tagged control is its own rendering
  // branch - a state-transition button, "Show body", and "Remove connection" each need their
  // own proof that the focus key is actually wired, not just that the mechanism works once.
  const { container, panel, done } = mountExtensionsPanel({
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
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

  done();
});

test("A run's id and proposal id are backend correlation identifiers; they must not appear in the run's primary...", async () => {
  // A run's id and proposal id are backend correlation identifiers; they must not appear in
  // the run's primary heading, only behind an explicit "Run details" disclosure.
  const { container, panel, done } = mountExtensionsPanel({
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
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

  done();
});

test("A \"get prompt\" result is a list of role-tagged messages, not the tool-shaped result every other operation...", async () => {
  // A "get prompt" result is a list of role-tagged messages, not the tool-shaped result every
  // other operation produces - it must render as readable message text, not the same raw JSON
  // block a tool result falls back to.
  const { container, panel, done } = mountExtensionsPanel({
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
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

  done();
});

test("A \"read resource\" result ({contents: [...]}) must render as a content preview - text inline, an image...", async () => {
  // A "read resource" result ({contents: [...]}) must render as a content preview - text
  // inline, an image inline - instead of the same raw JSON block a tool result falls back to.
  const { container, panel, done } = mountExtensionsPanel({
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", version: "1" }],
      families: { mcp: 1 },
    }),
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

  done();
});

test("extensions response fields must be read by the panel", async () => {
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
});

test("renderer must not duplicate backend trust policy", async () => {
  assert.ok(
    !extensionsPanel.includes("TRUST_TIERS"),
    "renderer must not duplicate backend trust policy",
  );
  assert.ok(
    !extensionsPanel.includes(".has(extension.family)"),
    "extension availability must not be inferred from its family",
  );
});

test("a slow catalog response must not overwrite a newer one", async () => {
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
});

test("the first change submits the revision it was shown", async () => {
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
});

test("a conflict must state that truth was reloaded", async () => {
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
});

test("an extension's unavailable explanation must be kept verbatim", async () => {
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
});

test("a body must not load during selection", async () => {
  const controller = createExtensionsPanelController({
    getExtensionDetail: async () => ({ extension_id: "skill:notes", body_available: true }),
    getExtensionBody: async () => ({ extension_id: "skill:notes", body: "the body" }),
  });
  await controller.selectExtension("skill:notes");
  assert.equal(controller.snapshot().body, "", "a body must not load during selection");
  await controller.loadBody("skill:notes");
  assert.equal(controller.snapshot().body, "the body", "a body loads only when asked for");
});

test("a retired extension must not offer state controls", async () => {
  assert.equal(extensionStateEnabled({ extension_id: "skill:notes", state: "enabled" }, false), true);
  assert.equal(extensionStateEnabled({ extension_id: "skill:notes", state: "enabled" }, true), false);
  assert.equal(
    extensionStateEnabled({ extension_id: "skill:notes", state: "retired" }, false),
    false,
    "a retired extension must not offer state controls",
  );
});

test("extension activity state must follow backend readiness", async () => {
  for (const [extension, expected] of [
    [null, "idle"],
    [{ state: "enabled", availability: "available", readiness: "ready" }, "ready"],
    [{ state: "enabled", availability: "available", readiness: "degraded" }, "degraded"],
    [{ state: "disabled", availability: "disabled", readiness: "unavailable" }, "blocked"],
    [{ state: "retired", availability: "available", readiness: "ready" }, "retired"],
  ]) {
    assert.equal(extensionActivityState(extension), expected);
  }
});

test("extension origin must show family, trust, and version", async () => {
  assert.equal(
    formatExtensionOrigin({ family: "skill", trust: "external", version: "2" }),
    "skill · external · v2",
  );
});

test("extensions must render list and detail in separate columns", async () => {
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
});

test("OAuth: the backend holds the verifier and state; the desktop carries only the code back", async () => {
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
});

test("\"Forget authorization\" clears the client's stored token; the panel must refresh oauth status from the...", async () => {
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
});

test("\"Disconnect\" ends the held session without touching the definition or stored credentials - distinct from...", async () => {
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
});

test("Disconnect is offered for any MCP connection regardless of current health, unlike \"Forget authorization\"...", async () => {
  // Disconnect is offered for any MCP connection regardless of current health, unlike
  // "Forget authorization" which only appears once OAuth is configured and authorized.
  const { container, panel, done } = mountExtensionsPanel({
    getExtensionDetail: async () => ({ extension_id: "mcp:probe", family: "mcp", state: "enabled" }),
    getExtensionRuntime: async () => ({ operations: [], snapshot: null }),
    getExtensionRuns: async () => ({ runs: [] }),
  });
  await panel.open();
  await panel.controller.selectExtension("mcp:probe");

  const buttons = findElements(container, (node) => node.tagName === "button").map((node) => node.textContent);
  assert.ok(buttons.includes("Disconnect"), "an MCP connection must always offer Disconnect regardless of its current health");

  done();
});

test("A probe reproduced the panel displaying the cached discovery snapshot's \"ready\" health as if it were...", async () => {
  // A probe reproduced the panel displaying the cached discovery snapshot's "ready"
  // health as if it were current, even after Disconnect had already closed the live
  // session (`connected: false`). The rendered label must reflect the live signal, not
  // the stale cached one.
  const { container, panel, done } = mountExtensionsPanel({
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

  done();
});

test("The \"Forget authorization\" control only appears once authorized - there is nothing to forget before then,...", async () => {
  // The "Forget authorization" control only appears once authorized - there is nothing to
  // forget before then, and Connect/Reconnect already cover that state.
  const { container, panel, done } = mountExtensionsPanel({
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

  done();
});

test("an unauthorized OAuth connection has no stored authorization to forget", async () => {
  const { container, panel, done } = mountExtensionsPanel({
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

  done();
});

test("Completing without a started flow must not invent a state value", async () => {
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
});

test("Cancelling a run is confirmed, and declining leaves the run alone", async () => {
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
});

test("owner controls must follow provenance, and the MCP credential form must not wait for discovery", async () => {
  async function controlsFor(family, localId, provenance, trust) {
    const extensionId = `${family}:${localId}`;
    const { container, panel, done } = mountExtensionsPanel({
      getExtensions: async () => ({
        extensions: [{ extension_id: extensionId, display_name: localId, family, trust, provenance, version: "1" }],
        families: { [family]: 1 },
      }),
      getExtensionDetail: async () => ({
        extension_id: extensionId, family, local_id: localId, trust, provenance, state: "enabled",
      }),
      getExtensionRuntime: async () => ({ operations: [] }),
      getExtensionOauth: async () => ({ configured: false, authorized: false }),
    });
    try {
      await panel.open();
      await panel.controller.selectExtension(extensionId);
      return findElements(container, (node) => typeof node.textContent === "string").map((node) => node.textContent);
    } finally {
      done();
    }
  }
  const operatorConnection = await controlsFor("mcp", "weather", "data/extensions/mcp", "external");
  assert.ok(operatorConnection.includes("Credential"), "a connection with no discovered operations must still offer its credential form");
  assert.ok(operatorConnection.includes("Remove connection"), "an operator-owned connection must be removable");
  assert.ok(!(await controlsFor("mcp", "builtin", "config/extensions/mcp", "application")).includes("Remove connection"),
    "an application connection must not be removable");

  assert.ok((await controlsFor("tool", "writer", "data/extensions/tools", "external")).includes("Remove tool"));
  assert.ok(!(await controlsFor("tool", "writer", "config/extensions/tools", "application")).includes("Remove tool"),
    "an application tool must not be removable");

  assert.ok((await controlsFor("skill", "notes", "data/extensions/skills", "external")).includes("Edit skill"),
    "an operator skill carries external trust and must still be editable");
  assert.ok(!(await controlsFor("skill", "notes", "config/extensions/skills", "operator")).includes("Edit skill"),
    "ownership follows provenance, not trust");
});

test("the desktop must never handle a PKCE verifier", async () => {
  const panel = readFileSync(new URL("../src/components/extensions-panel.js", import.meta.url), "utf8");
  assert.ok(!panel.includes("code_verifier"), "the desktop must never handle a PKCE verifier");
});

test("Operator skills are editable through the governed capability, not a direct write", async () => {
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
});

test("a refused extension change must surface the backend's reason, not claim success", async () => {
  const cases = [
    ["saveSkill", ["rogue", "---\nname: rogue\n---\nbody"], "detailError", "skill declares an authority-bearing field", "Skill saved."],
    ["importSkill", ["rogue", "---\nname: rogue\n---\nbody"], "importSkillError", "skill declares an authority-bearing field", "Skill imported."],
    ["removeSkill", ["notes"], "detailError", "skill is referenced by an enabled agent", "Skill removed."],
    ["removeLocalTool", ["changelog-writer"], "detailError", "tool is referenced by an enabled agent", "Local tool removed."],
    ["addMcpConnection", [{ localId: "bad", name: "Bad", url: "https://x.test/mcp" }], "addConnectionError", "MCP definition has unknown fields: bogus", "MCP connection added."],
    ["removeMcpConnection", ["weather"], "detailError", "connection is referenced by an enabled agent", "MCP connection removed."],
  ];
  for (const [operation, args, errorField, reason, successNotice] of cases) {
    const controller = createExtensionsPanelController({
      getExtensions: async () => ({ extensions: [], families: {} }),
      proposeAction: async () => ({ status: "failure", execution: { error: reason } }),
    });
    await controller[operation](...args);
    const snapshot = controller.snapshot();
    assert.ok(snapshot[errorField].includes(reason), `${operation} must show the backend's reason`);
    assert.notEqual(snapshot.notice, successNotice, `${operation} must not report success`);
  }
});

test("a malformed extension ID must never reach the backend", async () => {
  const cases = [
    ["addLocalTool", { localId: "Not A Valid Id!", name: "Bad", command: "python3", argvAllowlist: "python3", workingRoot: "data" }, "addToolError", /Tool ID/],
    ["addMcpConnection", { localId: "Not A Valid Id!", name: "Bad", url: "https://x.test/mcp" }, "addConnectionError", /Connection ID/],
    ["importSkill", "Not A Valid Id!", "importSkillError", /Skill ID/],
  ];
  for (const [operation, input, errorField, message] of cases) {
    const proposals = [];
    const controller = createExtensionsPanelController({
      getExtensions: async () => ({ extensions: [], families: {} }),
      proposeAction: async (request) => { proposals.push(request); return { status: "success" }; },
    });
    await (operation === "importSkill" ? controller.importSkill(input, "---\nname: Bad\n---\nbody") : controller[operation](input));
    assert.equal(proposals.length, 0, `${operation} must not propose a malformed ID`);
    assert.match(controller.snapshot()[errorField], message);
  }
});

test("A loaded skill body must actually appear in the Edit skill textarea. The editor renders unconditionally...", async () => {
  // A loaded skill body must actually appear in the Edit skill textarea. The editor renders
  // unconditionally (before any body is loaded) with an empty draft-keyed value, so the
  // capture-then-restore re-render mechanism must not stomp the freshly loaded body back to
  // that pre-load empty value on the very re-render that first populates it.
  const { container, panel, done } = mountExtensionsPanel({
    getExtensions: async () => ({
      extensions: [{ extension_id: "skill:notes", display_name: "Notes", family: "skill", trust: "operator", provenance: "data/extensions", version: "1" }],
      families: { skill: 1 },
    }),
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

  done();
});

test("An operator can add an MCP connection without hand-editing YAML: the same governed capability path as...", async () => {
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
});

test("An operator can scope a new connection to specific tools/resources/prompts without sending an empty...", async () => {
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
});

test("an empty item between commas must be dropped", async () => {
  assert.deepEqual(parseAllowlist("a, b ,  c"), ["a", "b", "c"]);
  assert.deepEqual(parseAllowlist(""), []);
  assert.deepEqual(parseAllowlist(null), []);
  assert.deepEqual(parseAllowlist("a,,b"), ["a", "b"], "an empty item between commas must be dropped");
});

test("a blank line between tokens must be dropped", async () => {
  assert.deepEqual(parseCommandLines("python3\n-m\nscripts.changelog"), ["python3", "-m", "scripts.changelog"]);
  assert.deepEqual(parseCommandLines(""), []);
  assert.deepEqual(parseCommandLines(null), []);
  assert.deepEqual(parseCommandLines("python3\n\n-m\n"), ["python3", "-m"], "a blank line between tokens must be dropped");
});

test("An operator can add a governed local tool without hand-editing YAML, the same governed capability path...", async () => {
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
});

test("Editing an MCP connection reuses the same write capability Add uses, but must carry the fingerprint the...", async () => {
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
});

test("A stale editor's conflict must surface as the backend's reason, keep the form open for retry, and never...", async () => {
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
});

test("Cancelling an edit closes the form without proposing anything", async () => {
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
});

test("Add and Edit MCP Connection both expose credential_ref and OAuth fields directly, so saving carries...", async () => {
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
});

test("Explicitly clearing credential_ref/oauth on an edit must actually clear them, not leave the base value in...", async () => {
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
});

test("OAuth requires at minimum a client_id; every other field is optional and the backend discovers...", async () => {
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
});

test("Editing a local tool follows the same contract as editing an MCP connection", async () => {
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
});

test("A saved edit must preserve skill_id/script - what makes a tool run a skill's declared script rather than...", async () => {
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
});

test("A tool always registers as privileged_execution, and boundaries.py refuses a privileged_execution...", async () => {
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
});

test("extension_runtime_service.py's _mcp wraps every non-discover result as {content: result, trusted: false} -...", async () => {
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
});

test("a tool-shaped result has no contents array and must not be misread as a resource result", async () => {
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
});

test("The Add MCP Connection control must render as a real, human-labeled form, not raw JSON, and its submit...", async () => {
  // The Add MCP Connection control must render as a real, human-labeled form, not raw
  // JSON, and its submit must reach the governed capability with typed arguments.
  const proposals = [];
  const { container, panel, done } = mountExtensionsPanel({
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

  done();
});

test("Edit MCP Connection: clicking \"Edit connection\" loads the stored definition and renders a form prefilled...", async () => {
  // Edit MCP Connection: clicking "Edit connection" loads the stored definition and renders a
  // form prefilled from it (not the empty Add form), and submitting reaches the governed
  // capability carrying the fingerprint the definition was read with.
  const proposals = [];
  const { container, panel, done } = mountExtensionsPanel({
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", provenance: "data/extensions", version: "1" }],
      families: { mcp: 1 },
    }),
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

  done();
});

test("Edit MCP Connection must prefill credential reference and OAuth fields from the loaded definition, and an...", async () => {
  // Edit MCP Connection must prefill credential reference and OAuth fields from the loaded
  // definition, and an unrelated field edit (display name) must leave an untouched
  // credential/OAuth configuration intact - the round trip that makes these fields safe to
  // expose without an operator accidentally erasing authentication on every save.
  const proposals = [];
  const { container, panel, done } = mountExtensionsPanel({
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:weather", display_name: "Weather", family: "mcp", trust: "operator", provenance: "data/extensions", version: "1" }],
      families: { mcp: 1 },
    }),
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

  done();
});

test("Add MCP Connection must also expose credential reference and OAuth fields, so a new connection can be...", async () => {
  // Add MCP Connection must also expose credential reference and OAuth fields, so a new
  // connection can be fully configured without a follow-up edit.
  const proposals = [];
  const { container, panel, done } = mountExtensionsPanel({
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

  done();
});

test("Add MCP Connection for a stdio transport must build the same command/process shape Add Local Tool already...", async () => {
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
});

test("Editing a stdio connection must preserve its transport (not switch it), and an edit that changes the...", async () => {
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
});

test("The Add MCP Connection form's transport select must toggle between the streamable_http and stdio field...", async () => {
  // The Add MCP Connection form's transport select must toggle between the streamable_http and
  // stdio field sets, and submitting with stdio selected must reach the governed capability
  // with the argv-shaped definition instead of the URL-shaped one.
  const proposals = [];
  const { container, panel, done } = mountExtensionsPanel({
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

  done();
});

test("Edit MCP Connection for a stdio connection must render the stdio field set (command, argv allowlist,...", async () => {
  // Edit MCP Connection for a stdio connection must render the stdio field set (command, argv
  // allowlist, environment passthrough, working root), not the streamable_http url field.
  const proposals = [];
  const { container, panel, done } = mountExtensionsPanel({
    getExtensions: async () => ({
      extensions: [{ extension_id: "mcp:local-tool-server", display_name: "Local tool server", family: "mcp", trust: "operator", provenance: "data/extensions", version: "1" }],
      families: { mcp: 1 },
    }),
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

  done();
});

test("The Add Local Tool control must render as a real, human-labeled form, not raw JSON, and its submit must...", async () => {
  // The Add Local Tool control must render as a real, human-labeled form, not raw JSON,
  // and its submit must reach the governed capability with typed, argv-shaped arguments.
  const proposals = [];
  const { container, panel, done } = mountExtensionsPanel({
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

  done();
});

test("Edit Local Tool: clicking \"Edit tool\" loads the stored definition and renders a form prefilled from it,...", async () => {
  // Edit Local Tool: clicking "Edit tool" loads the stored definition and renders a form
  // prefilled from it, and submitting reaches the governed capability with the fingerprint.
  const proposals = [];
  const { container, panel, done } = mountExtensionsPanel({
    getExtensions: async () => ({
      extensions: [{ extension_id: "tool:changelog-writer", display_name: "Changelog writer", family: "tool", trust: "operator", provenance: "data/extensions", version: "1" }],
      families: { tool: 1 },
    }),
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

  done();
});

test("An operator can import a brand-new skill without hand-editing YAML, distinct from saveSkill's...", async () => {
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
});

test("The Import Skill control must render as a real form, not raw JSON, and its submit must reach the governed...", async () => {
  // The Import Skill control must render as a real form, not raw JSON, and its submit
  // must reach the governed capability with typed arguments.
  const proposals = [];
  const { container, panel, done } = mountExtensionsPanel({
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

  done();
});

test("main.js must wire every handler extensions-panel.js actually calls. getExtensionDefinition was missing...", async () => {
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
});

test("extension ids must follow the backend's local id rule", async () => {
  const contracts = readFileSync(new URL("../../backend/app/extensions/contracts.py", import.meta.url), "utf8");
  const backendRule = new RegExp(contracts.match(/SAFE_LOCAL_ID = re\.compile\(r"([^"]+)"\)/)[1]);
  for (const id of ["weather", "notes-2", "a.b_c", "0x", "Weather", "-lead", "../up", "has space", ""]) {
    assert.equal(extensionLocalIdValid(id), backendRule.test(id), `desktop and backend must agree on ${JSON.stringify(id)}`);
  }
});

test("tool results and run titles must render for the operator", async () => {
  assert.equal(formatToolResult({ content: { content: [{ type: "text", text: "one" }, { type: "text", text: "two" }] } }), "one\ntwo");
  assert.equal(formatToolResult({ content: { content: [{ type: "image", data: "x" }] } }), null, "non-text content must use the generic view");
  assert.equal(formatToolResult({}), null);
  assert.equal(extensionRunTitle({ extension_name: "Weather", operation: "discover", status: "awaiting_input" }),
    "Weather · Discover tools and resources · awaiting input");
  assert.equal(extensionRunTitle({ extension_name: "Weather" }), "Weather · unknown");
});
