import { test } from "node:test";
import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { agentCancelNotice, agentInvokeEnabled, agentInvokeNotice, agentModesSummary, agentRunActivityState, agentRunProfileId, agentToolLabel, createAgentsPanelController, profileIdFromName, agentFormErrors, agentFormFromProfile, agentProfileFromForm, duplicateAgentForm, newAgentForm } from "../src/components/agents-panel.js";
import { agentProfile, agentRunRecord, deferred } from "./support.mjs";

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
  assert.equal(agentFormErrors({ ...valid, runtime_kind: "acp" }), "Name the external agent definition it runs in.");

  const acp = agentProfileFromForm({ ...valid, runtime_kind: "acp", adapter_id: " agent ", cancellable: false });
  assert.deepEqual(acp.runtime, { kind: "acp", adapter_id: "agent" });
  assert.equal(acp.cancellable, true, "an ACP-run agent is always cancellable");
});
