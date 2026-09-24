import { test } from "node:test";
import { strict as assert } from "node:assert";
import { actionApprovalEnabled, capabilityActivityState, capabilityArgumentFields, coerceArguments, createActionsPanel, createActionsPanelController, proposeEnabled, proposeTriggerLabel, executionActivityState, formatCapabilityApproval, formatCapabilityRisk } from "../src/components/actions-panel.js";
import { apiClient, actionsPanel, backend, createElement, deferred, findElement, findElements } from "./support.mjs";

test("an allow capability must offer a Run control, not a self-approval Propose control", async () => {
  const previousDocument = globalThis.document;
  globalThis.document = { createElement };
  try {
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
  } finally {
    globalThis.document = previousDocument;
  }
});

test("actions response fields must be read by the panel", async () => {
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
});

test("renderer must not duplicate backend approval policy", async () => {
  assert.ok(
    !actionsPanel.includes("APPROVABLE_STATES"),
    "renderer must not duplicate backend approval policy",
  );
  assert.ok(
    !actionsPanel.includes(".has(pending.status)"),
    "approval availability must not be inferred from a status string",
  );
});

test("a slow pending response must not overwrite a newer one", async () => {
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
});

test("the mutation lock must release after a decision", async () => {
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
});

test("a rejected decision must surface the backend reason", async () => {
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
});

test("a declined cancellation must not reach the backend", async () => {
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
});

test("the panel must retain the backend explanation verbatim", async () => {
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
});

test("an in-flight mutation must disable approval", async () => {
  assert.equal(actionApprovalEnabled({ proposal_id: "p1" }, false), true);
  assert.equal(actionApprovalEnabled({ proposal_id: "p1" }, true), false, "an in-flight mutation must disable approval");
  assert.equal(actionApprovalEnabled(null, false), false);
});

test("outcome_unknown must render distinctly from an ordinary failure, not fall through to it", async () => {
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
});

test("capability readiness and risk must render their backend state", async () => {
  for (const [capability, expected] of [
    [{ availability: "available", readiness: "ready" }, "ready"],
    [{ availability: "available", readiness: "degraded" }, "degraded"],
    [{ availability: "disabled", readiness: "unavailable" }, "blocked"],
  ]) {
    assert.equal(capabilityActivityState(capability), expected);
  }
});

test("destructive_action · approval required", async () => {
  assert.equal(
    formatCapabilityRisk({ effect_class: "destructive_action", authorization_rule: "requires_approval" }),
    "destructive_action · approval required",
  );
});

test("a turn-boundary capability must not look operator-drivable", async () => {
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
});

test("the propose trigger must say Run for allowed capabilities", async () => {
  assert.equal(proposeTriggerLabel({ authorization_rule: "requires_approval" }), "Propose");
  assert.equal(proposeTriggerLabel({ authorization_rule: "allow" }), "Run");
});

test("Only backend-reported facts may gate the propose control", async () => {
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
});

test("typed arguments must reach the backend as their declared types", async () => {
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
});

test("the propose form must submit the selected capability's arguments", async () => {
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
});

test("a malformed argument must never reach the backend", async () => {
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
});

test("the capability catalog must report descriptors it could not register", async () => {
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
});
