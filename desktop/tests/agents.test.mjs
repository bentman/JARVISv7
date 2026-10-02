import { test } from "node:test";
import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { CONNECTION_TEST_PROMPT, acpDefinitionStatus, acpMessageText, agentOutputText, agentProposalId, agentCancelNotice, agentInvokeEnabled, agentInvokeNotice, agentModesSummary, agentRunActivityState, agentRunProfileId, agentToolLabel, createAgentsPanel, createAgentsPanelController, profileIdFromName, agentFormErrors, agentFormFromProfile, agentProfileFromForm, duplicateAgentForm, newAgentForm } from "../src/components/agents-panel.js";
import { agentProfile, agentRunRecord, createElement, deferred, findElement } from "./support.mjs";

test("agent runs must derive the profile from the capability id", async () => {
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
});

test("the agent catalog must be unwrapped from its list envelope", async () => {
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
});

test("a failed invocation must report as an error", async () => {
  const controller = createAgentsPanelController({
    invokeAgent: async () => { throw new Error("agent capability is not authorized"); },
    listAgentRuns: async () => ({ records: [] }),
  });
  await controller.invoke("researcher", "go");
  const failed = controller.snapshot();
  assert.equal(failed.mutationError, "agent capability is not authorized", "a failed invocation must report as an error");
  assert.equal(failed.notice, "", "a failed invocation must not also read as a success notice");
  assert.equal(failed.mutationPending, false);
});

test("deleting an agent must be confirmed, and a conflicting delete must reload the catalog", async () => {
  const editable = { ...agentProfile, editable: true, fingerprint: "f1" };
  let listReads = 0;
  const deletes = [];
  const conflict = Object.assign(new Error("agent profile changed since it was read"), { status: 409 });
  const controller = createAgentsPanelController({
    listAgents: async () => { listReads += 1; return { agents: [editable] }; },
    deleteAgent: async (...args) => { deletes.push(args); throw conflict; },
  });
  await controller.refreshAgents();
  const prompts = [];
  await controller.remove("researcher", async (message) => { prompts.push(message); return false; });
  assert.equal(prompts.length, 1, "deleting must ask first");
  assert.deepEqual(deletes, [], "a declined confirmation must not delete");

  const readsBefore = listReads;
  await controller.remove("researcher", async () => true);
  assert.deepEqual(deletes, [["researcher", "f1"]]);
  const snapshot = controller.snapshot();
  assert.match(snapshot.mutationError, /changed since it was read.*reloaded/, "a conflict must say why and that the list was reloaded");
  assert.ok(listReads > readsBefore, "a conflict must reload the catalog");
});

test("stale agent responses must not replace a newer catalog", async () => {
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
});

test("an unavailable registry must be surfaced, not hidden", async () => {
  const controller = createAgentsPanelController({
    listAgents: async () => { throw new Error("agent registry is unavailable"); },
  });
  await controller.refreshAgents();
  assert.equal(controller.snapshot().agentsError, "agent registry is unavailable", "an unavailable registry must be surfaced, not hidden");
});

test("a disabled agent must not be invoked", async () => {
  const operatorAgent = {
    ...agentProfile,
    profile_id: "notes",
    source: "data/agents/notes.yaml",
    editable: true,
    enabled: true,
    fingerprint: "fp-1",
  };
  const applicationAgent = {
    ...agentProfile,
    output_contract: { type: "object", properties: { summary: { type: "string" } } },
    editable: false,
    enabled: true,
    fingerprint: "fp-app",
  };
  assert.equal(agentInvokeEnabled({ ...agentProfile, enabled: false }, "go", false), false, "a disabled agent must not be invoked");
  assert.equal(profileIdFromName("  Meeting Notes! v2 "), "meeting-notes-v2");
  assert.equal(
    agentModesSummary(["direct", "handoff"]),
    "Run it from this panel · Let it take over the conversation",
    "invocation modes must be described in operator language, not internal ids",
  );

  const calls = [];
  const created = [];
  const controller = createAgentsPanelController({
    listAgents: async () => ({ agents: [operatorAgent, applicationAgent] }),
    listAgentRuns: async () => ({ records: [] }),
    createAgent: async (profile) => { calls.push(["create", profile.profile_id]); created.push(profile); return { profile_id: profile.profile_id }; },
    updateAgent: async (...args) => { calls.push(["update", args[0], args[2]]); return { profile_id: args[0] }; },
    deleteAgent: async (...args) => { calls.push(["delete", ...args]); return { removed: true }; },
    setExtensionState: async (...args) => { calls.push(["state", ...args]); return {}; },
  });
  await controller.load();

  controller.startEdit(applicationAgent.profile_id);
  assert.equal(controller.snapshot().editing, "", "a built-in profile must not open an editor");

  controller.startCreate();
  controller.setField("display_name", "Meeting Notes");
  await controller.save();
  assert.equal(controller.snapshot().mutationError, "Say what the agent is for.", "a missing field must be reported before any request");
  assert.deepEqual(calls, []);

  controller.setField("purpose", "Tidy meeting notes");
  controller.setField("instructions", "Answer briefly.");
  controller.setMode("handoff", true);
  controller.setField("approval_class", "none");
  await controller.save();
  assert.deepEqual(
    [created[0].profile_id, created[0].invocation_modes, created[0].approval_class, created[0].runtime],
    ["meeting-notes", ["direct", "handoff"], "none", { kind: "internal" }],
    "a new agent's id comes from its name and its choices become the profile",
  );

  controller.startDuplicate(applicationAgent.profile_id);
  assert.equal(controller.snapshot().form.display_name, "Researcher (copy)");
  controller.setMode("router_selected", true);
  await controller.save();
  assert.equal(created[1].profile_id, "researcher-copy", "a duplicate of a built-in agent becomes the operator's own profile");
  assert.deepEqual(created[1].output_contract, applicationAgent.output_contract, "a duplicate keeps the fields the form does not show");
  assert.ok(!("fingerprint" in created[1]) && !("editable" in created[1]), "response-only fields must not be sent back as profile content");

  controller.startEdit("notes");
  await controller.save();
  await controller.remove("notes");
  await controller.setEnabled("researcher", false);
  assert.deepEqual(calls, [
    ["create", "meeting-notes"],
    ["create", "researcher-copy"],
    ["update", "notes", "fp-1"],
    ["delete", "notes", "fp-1"],
    ["state", "agent:researcher", "disabled"],
  ], "edits and deletes must carry the fingerprint that was read; enablement uses the agent's extension id");
  assert.equal(controller.snapshot().editing, "", "a saved profile must close the editor");
  assert.equal(controller.snapshot().notice, "Agent disabled.");
});

test("a tool must say when it needs approval or cannot run", async () => {
  assert.equal(
    agentToolLabel({ label: "mcp:notes tool:save", needs_approval: true, available: false }),
    "mcp:notes tool:save (asks you first, unavailable now)",
    "a tool must say when it needs approval or cannot run",
  );
  const created = [];
  const controller = createAgentsPanelController({
    listAgents: async () => ({ agents: [] }),
    listAgentRuns: async () => ({ records: [] }),
    listAgentTools: async () => ({ tools: [{ capability_id: "ext-read", label: "mcp:notes tool:read", needs_approval: false, available: true }] }),
    createAgent: async (profile) => { created.push(profile); return { profile_id: profile.profile_id }; },
  });
  await controller.load();
  await controller.startCreate();
  assert.deepEqual(controller.snapshot().tools.map((tool) => tool.capability_id), ["ext-read"], "opening the form loads the tools an agent may be allowed");
  controller.setField("display_name", "Reader");
  controller.setField("purpose", "Read notes");
  controller.setField("instructions", "Answer from the notes.");
  controller.setField("memory_scope", "semantic");
  controller.setTool("ext-read", true);
  await controller.save();
  assert.deepEqual(
    [created[0].memory_scope, created[0].capability_ids],
    ["semantic", ["ext-read"]],
    "the memory an agent may read and the tools it may use become its profile",
  );
});

test("the agent form must produce exactly the backend AgentProfile fields", async () => {
  const schema = readFileSync(new URL("../../backend/app/agents/schema.py", import.meta.url), "utf8");
  const profileClass = schema.slice(schema.indexOf("class AgentProfile:"));
  const fields = [...profileClass.slice(0, profileClass.indexOf("def ")).matchAll(/^    ([a-z_]+): /gm)].map((m) => m[1]);
  assert.ok(fields.includes("profile_id") && fields.includes("runtime"), "the schema scan must find the AgentProfile fields");

  const form = newAgentForm();
  assert.equal(agentFormErrors(form), "Give the agent a name.");
  Object.assign(form, { display_name: "Meeting Notes!", purpose: "Tidy notes", instructions: "Answer briefly." });
  assert.equal(agentFormErrors(form), "");

  const profile = agentProfileFromForm(form);
  assert.deepEqual(Object.keys(profile).sort(), [...fields].sort(), "the form must send every schema field and nothing else");
  assert.equal(profile.profile_id, "meeting-notes", "an empty id must derive from the name");
  assert.deepEqual(profile.invocation_modes, ["direct"]);
  assert.equal(profile.timeout_ms, 30000);
  assert.deepEqual(profile.runtime, { kind: "internal" });
});

test("editing an agent must round-trip its profile and drop response-only fields", async () => {
  const listed = { ...agentProfile, timeout_ms: 45000, output_contract: { type: "object" }, provider_model_policy: {},
    runtime: { kind: "internal" }, source: "data/agents/researcher.yaml", editable: true, enabled: true, fingerprint: "abc" };
  const form = agentFormFromProfile(listed);
  assert.equal(form.timeout_seconds, 45);
  const saved = agentProfileFromForm(form);
  for (const field of ["source", "editable", "enabled", "fingerprint"]) {
    assert.equal(field in saved, false, `${field} is response metadata and must not be saved back`);
  }
  const { source, editable, enabled, fingerprint, ...document } = listed;
  assert.deepEqual(saved, document);

  const copy = duplicateAgentForm(listed);
  assert.equal(copy.profile_id, "researcher-copy");
  assert.equal(copy.display_name, "Researcher (copy)");
});

test("the agent form must refuse incomplete input with the field to fix", async () => {
  const valid = { ...newAgentForm(), display_name: "Notes", purpose: "Tidy", instructions: "Briefly." };
  assert.equal(agentFormErrors({ ...valid, display_name: "!!!" }), "The name needs at least one letter or number.");
  assert.equal(agentFormErrors({ ...valid, purpose: " " }), "Say what the agent is for.");
  assert.equal(agentFormErrors({ ...valid, instructions: "" }), "Tell the agent how to work.");
  assert.equal(agentFormErrors({ ...valid, modes: [] }), "Choose at least one way to reach the agent.");
  for (const seconds of [0, 601, 1.5, "x"]) {
    assert.equal(agentFormErrors({ ...valid, timeout_seconds: seconds }), "The time limit must be a whole number of seconds from 1 to 600.");
  }
  assert.equal(agentFormErrors({ ...valid, runtime_kind: "acp" }), "Choose the external agent definition it runs in.");

  const acp = agentProfileFromForm({ ...valid, runtime_kind: "acp", adapter_id: " agent ", cancellable: false });
  assert.deepEqual(acp.runtime, { kind: "acp", adapter_id: "agent" });
  assert.equal(acp.cancellable, true, "an ACP-run agent is always cancellable");
});

test("agent output and linked runs must be read from where the backend puts them", async () => {
  const records = [
    { kind: "action_proposal", capability_id: "agent-invoke-coder", proposal_id: "p2" },
    { kind: "execution_result", capability_id: "agent-invoke-coder", proposal_id: "p1" },
    { kind: "action_proposal", capability_id: "agent-invoke-coder", proposal_id: "p1" },
    { kind: "action_proposal", capability_id: "agent-invoke-other", proposal_id: "p0" },
  ];
  assert.equal(agentProposalId(records, "coder"), "p2", "the newest invocation of that agent");
  assert.equal(agentProposalId(records.slice(1), "coder", { unfinished: true }), "", "a finished run is not in flight");
  assert.equal(agentProposalId(records, "coder", { unfinished: true }), "p2");
  const events = [
    { kind: "session_update", update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "rea" } } },
    { kind: "session_update", update: { sessionUpdate: "tool_call", title: "read" } },
    { kind: "session_update", update: { session_update: "agent_message_chunk", content: { type: "text", text: "dy" } } },
    { kind: "permission_selected", option_id: "allow" },
  ];
  assert.equal(acpMessageText(events), "ready", "an external agent's reply is its streamed message chunks");
  assert.equal(agentOutputText({ output: { response: " done " } }), "done", "an internal agent's reply is its response");
  assert.equal(agentOutputText({ output: { stopReason: "end_turn" } }, { events }), "ready");
  const definition = { extension_id: "acp:coder", state: "enabled", availability: "available", readiness: "ready" };
  assert.equal(acpDefinitionStatus(definition, { connected: true }), "Ready · connected");
  assert.equal(acpDefinitionStatus({ ...definition, state: "disabled" }), "Disabled in Extensions");
  assert.equal(acpDefinitionStatus(null), "Not found in Extensions");
});

test("a running agent must stay cancellable, answerable, and linked to its external run", async () => {
  const calls = [];
  const running = deferred();
  const acpAgent = { ...agentProfile, profile_id: "coder", runtime: { kind: "acp", adapter_id: "coder" }, enabled: true };
  let agentRecords = [];
  let extensionRuns = [];
  const controller = createAgentsPanelController({
    listAgents: async () => ({ agents: [acpAgent], problems: [{ capability_id: "agent-invoke-broken", reason: "unknown ACP definition" }] }),
    listAgentRuns: async () => ({ records: agentRecords }),
    getExtensions: async () => ({ extensions: [
      { extension_id: "acp:coder", family: "acp", display_name: "Coder", state: "enabled", availability: "available", readiness: "ready" },
      { extension_id: "mcp:notes", family: "mcp", name: "Notes" },
    ] }),
    getExtensionRuntime: async () => ({ connected: false, operations: [] }),
    getExtensionRuns: async () => ({ runs: extensionRuns }),
    invokeAgent: (...args) => { calls.push(["invoke", ...args]); return running.promise; },
    cancelAction: async (...args) => { calls.push(["cancelAction", ...args]); return { proposal_id: args[0], cancelled: true }; },
    cancelAgent: async (...args) => { calls.push(["cancelAgent", ...args]); return { cancelled: false }; },
    answerExtensionInput: async (...args) => { calls.push(["answer", ...args]); },
  });
  await controller.load();
  const loaded = controller.snapshot();
  assert.deepEqual(loaded.problems.map((problem) => problem.reason), ["unknown ACP definition"], "profiles the registry refused must be reported");
  assert.deepEqual(loaded.acpDefinitions.map((item) => item.extension_id), ["acp:coder"], "only ACP definitions can host an external agent");
  controller.selectAgent("coder");

  const invocation = controller.invoke("coder", "fix the build");
  assert.equal(controller.snapshot().invokePending, true);
  assert.equal(controller.snapshot().mutationPending, false, "a running invocation must not hold the lock that disables Cancel");
  assert.equal(controller.hasLiveRun(), true, "the panel must follow a run while it is in flight");

  agentRecords = [{ kind: "action_proposal", capability_id: "agent-invoke-coder", proposal_id: "p7", record: {} }];
  extensionRuns = [{ run_id: "r1", extension_id: "acp:coder", proposal_id: "p7", status: "awaiting_input",
    request: { kind: "permission_request", request_id: "q1", options: [{ optionId: "allow", name: "Allow", kind: "allow_once" }] } }];
  await controller.poll();
  assert.equal(controller.snapshot().activeRun.proposalId, "p7", "polling must discover the in-flight run's proposal");
  assert.equal(controller.snapshot().extensionRuns[0].request.kind, "permission_request", "the external agent's permission request must reach the panel");

  await controller.answer("r1", "q1", { action: "accept", option_id: "allow" });
  await controller.cancel("coder");
  assert.deepEqual(calls.filter(([name]) => ["answer", "cancelAction", "cancelAgent"].includes(name)), [
    ["answer", "r1", "q1", { action: "accept", option_id: "allow" }],
    ["cancelAction", "p7"],
  ], "cancel must target the specific in-flight run, not guess from the audit");

  agentRecords = [{ kind: "execution_result", capability_id: "agent-invoke-coder", proposal_id: "p7", record: { status: "success" } }, ...agentRecords];
  extensionRuns = [{ ...extensionRuns[0], status: "success", request: null,
    events: [{ kind: "session_update", update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "Build fixed." } } }] }];
  running.resolve({ agent_id: "coder", status: "success", output: { stopReason: "end_turn" }, turn_id: "t1", session_id: "s1" });
  await invocation;
  const finished = controller.snapshot();
  assert.equal(finished.invokePending, false);
  assert.equal(finished.lastResult.proposalId, "p7", "the finished run must stay linked to its evidence");
  assert.equal(agentOutputText(finished.lastResult.payload, finished.extensionRuns[0]), "Build fixed.");
});

test("the rendered agent detail must expose connection testing, permission answers, and a definition picker", async () => {
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement, createTextNode: (text) => ({ textContent: text, children: [], dataset: {} }) };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  try {
    const acpAgent = { ...agentProfile, profile_id: "coder", display_name: "Coder", runtime: { kind: "acp", adapter_id: "coder" }, enabled: true, editable: true };
    const container = createElement("div");
    const panel = createAgentsPanel(container, {
      listAgents: async () => ({ agents: [acpAgent], problems: [{ capability_id: "agent-invoke-broken", reason: "unknown ACP definition" }] }),
      listAgentRuns: async () => ({ records: [{ ...agentRunRecord, capability_id: "agent-invoke-coder" }] }),
      listAgentTools: async () => ({ tools: [] }),
      getExtensions: async () => ({ extensions: [{ extension_id: "acp:coder", family: "acp", display_name: "Coder CLI", state: "enabled", availability: "available", readiness: "ready" }] }),
      getExtensionRuntime: async () => ({ connected: true, operations: [] }),
      getExtensionRuns: async () => ({ runs: [{ run_id: "r1", extension_id: "acp:coder", proposal_id: "p7", status: "awaiting_input",
        request: { kind: "permission_request", request_id: "q1", options: [{ optionId: "allow", name: "Allow", kind: "allow_once" }] } }] }),
    });
    await panel.open();
    assert.ok(findElement(container, (node) => node.textContent === "Could not load broken: unknown ACP definition"), "refused profiles must be listed");
    panel.controller.selectAgent("coder");
    await panel.controller.refreshRuntime("coder");
    const text = (value) => findElement(container, (node) => node.textContent === value);
    assert.ok(text("Ready · connected"), "an external agent must show its definition status");
    assert.ok(text("Test connection"), "an external agent must offer a connection test");
    assert.ok(text("Accept") && text("Allow (allow_once)"), "a pending permission request must be answerable from the agent detail");
    assert.ok(
      findElement(container, (node) => node.tagName === "li" && node.children[0]?.tagName === "strong" && node.children[0].textContent === "Coder"
        && node.children[1]?.className === "actions-audit-steps"),
      "a run must be titled by its agent's name and read as a timeline",
    );
    await panel.controller.startEdit("coder");
    const picker = findElement(container, (node) => node.tagName === "select" && node.name === "adapter_id");
    assert.deepEqual(picker.children.map((option) => [option.value, option.textContent]),
      [["", "Choose a definition…"], ["coder", "Coder CLI (Ready)"]], "the definition must be chosen from Extensions, not typed");
    panel.close();
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
  }
});

test("testing an external agent connection must report the reply or a readable failure", async () => {
  const replied = [{ extension_id: "acp:coder", proposal_id: "t1", status: "success",
    events: [{ kind: "session_update", update: { sessionUpdate: "agent_message_chunk", content: { type: "text", text: "ready" } } }] }];
  for (const [invokeResult, runs, expected, ok] of [
    [{ proposal_id: "t1", status: "success" }, replied, "Connected. It replied: ready", true],
    [{ proposal_id: "t2", status: "failure", execution: { error: "configured executable is unavailable" } }, [],
      "The test failed: configured executable is unavailable.", false],
  ]) {
    const sent = [];
    const controller = createAgentsPanelController({
      getExtensionRuntime: async () => ({ connected: false, operations: [{ name: "prompt", capability_id: "extension-abc" }] }),
      invokeExtension: async (...args) => { sent.push(args); return invokeResult; },
      getExtensionRuns: async () => ({ runs }),
    });
    assert.equal(await controller.testConnection("coder"), ok);
    assert.deepEqual(sent, [["acp:coder", "extension-abc", { prompt: CONNECTION_TEST_PROMPT }]], "the test must use the definition's own prompt operation");
    assert.deepEqual(controller.snapshot().test, { adapterId: "coder", pending: false, ok, message: expected });
  }
  const unpromptable = createAgentsPanelController({
    getExtensionRuntime: async () => ({ operations: [] }),
    invokeExtension: async () => { throw new Error("must not invoke"); },
  });
  assert.equal(await unpromptable.testConnection("coder"), false);
  assert.match(unpromptable.snapshot().test.message, /cannot be prompted/, "a definition with no prompt operation must say why");
});

test("agent form fields must have dataset.draftKey to preserve operator drafts across panel switches", async () => {
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;
  globalThis.document = { createElement, createTextNode: (text) => ({ textContent: text, children: [], dataset: {} }) };
  globalThis.window = { setInterval: () => 0, clearInterval() {} };
  try {
    const container = createElement("div");
    const panel = createAgentsPanel(container, {
      listAgents: async () => ({ agents: [{ ...agentProfile, editable: true }] }),
      listAgentRuns: async () => ({ records: [] }),
      listAgentTools: async () => ({ tools: [{ capability_id: "tool-1", label: "Tool 1" }] }),
    });
    await panel.open();
    await panel.controller.startEdit("researcher");

    const nameInput = findElement(container, (node) => node.tagName === "input" && node.name === "display_name");
    assert.ok(nameInput);
    assert.equal(nameInput.dataset.draftKey, "agent-form:display_name");

    const purposeInput = findElement(container, (node) => node.tagName === "input" && node.name === "purpose");
    assert.ok(purposeInput);
    assert.equal(purposeInput.dataset.draftKey, "agent-form:purpose");

    const instructionsInput = findElement(container, (node) => node.tagName === "textarea" && node.name === "instructions");
    assert.ok(instructionsInput);
    assert.equal(instructionsInput.dataset.draftKey, "agent-form:instructions");

    panel.close();
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
  }
});
