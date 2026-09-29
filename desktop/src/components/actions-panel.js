import { createRenderStateKeeper } from "./render-state.js";

const AUDIT_LIMITS = [10, 20, 50, 100];

function errorMessage(error, fallback) {
  return error?.detail?.message || error?.message || fallback;
}

function isConflict(error) {
  return error?.status === 409 || error?.detail?.error === "conflict";
}

export function actionApprovalEnabled(pending, mutationPending) {
  return Boolean(pending?.proposal_id) && !mutationPending;
}

export function executionActivityState(execution) {
  if (!execution) return "idle";
  if (execution.status === "success") return "succeeded";
  if (execution.status === "cancelled") return "cancelled";
  if (execution.status === "failure") return "failed";
  // A timeout or cancellation can leave the backend unable to tell whether the call
  // already ran - reported as "outcome_unknown" rather than "failure" so an operator is
  // not led to believe nothing happened and it is safe to repeat. Rendered as
  // "degraded" (the same caution styling already used elsewhere), not "failed", since
  // treating it as an ordinary failure is exactly the collapse this exists to avoid.
  if (execution.status === "outcome_unknown") return "degraded";
  return "running";
}

export function capabilityActivityState(capability) {
  if (!capability) return "idle";
  if (capability.availability !== "available") return "blocked";
  if (capability.readiness === "degraded") return "degraded";
  if (capability.readiness === "unavailable") return "blocked";
  return "ready";
}

export function proposeEnabled(capability, mutationPending) {
  // Only backend-reported facts gate the control; the renderer never decides authorization.
  return Boolean(
    capability?.executable
      && capability.availability === "available"
      && capability.approval_mode !== "turn_boundary"
      && !mutationPending,
  );
}

export function capabilityArgumentFields(inputSchema) {
  const properties = inputSchema?.properties || {};
  const required = new Set(inputSchema?.required || []);
  return Object.keys(properties).map((name) => {
    const types = [].concat(properties[name]?.type ?? "string");
    const type = types.find((item) => item !== "null") || "string";
    return { name, type, nullable: types.includes("null"), required: required.has(name) };
  });
}

export function coerceArguments(fields, values) {
  const args = {};
  for (const field of fields) {
    const raw = values[field.name];
    if (field.type === "boolean") {
      if (raw === undefined && !field.required) continue;
      args[field.name] = Boolean(raw);
      continue;
    }
    const text = raw === undefined || raw === null ? "" : String(raw).trim();
    if (text === "") {
      if (field.nullable && field.required) args[field.name] = null;
      else if (field.required) args[field.name] = "";
      continue;
    }
    if (field.type === "integer" || field.type === "number") {
      const parsed = Number(text);
      if (!Number.isFinite(parsed)) throw new Error(`${field.name} must be a number.`);
      args[field.name] = field.type === "integer" ? Math.trunc(parsed) : parsed;
      continue;
    }
    if (field.type === "object" || field.type === "array") {
      try {
        args[field.name] = JSON.parse(text);
      } catch {
        throw new Error(`${field.name} must be valid JSON.`);
      }
      continue;
    }
    args[field.name] = text;
  }
  return args;
}

export function formatCapabilityApproval(capability) {
  if (!capability) return "";
  // A turn_boundary capability is proposed and executed inside a conversation turn, so the
  // operator surface can only report it, never drive it.
  if (capability.approval_mode === "turn_boundary") return "approved in conversation";
  // An "allow" capability runs immediately with no decision to describe; labeling it as if it
  // were approved would misrepresent a plain local action as a self-approval ritual.
  return capability.authorization_rule === "requires_approval" ? "requires approval" : "";
}

export function proposeTriggerLabel(capability) {
  return capability?.authorization_rule === "requires_approval" ? "Propose" : "Run";
}

const EFFECT_TEXT = {
  local_read: "Reads local data",
  local_write: "Changes local data",
  external_read: "Reads from an external service",
  external_write: "Sends data to an external service",
  cloud_model: "Sends context to a cloud model",
  privileged_execution: "Runs a program on this computer",
  destructive_action: "Deletes or replaces data",
};

const AVAILABILITY_TEXT = {
  disabled: "Disabled.",
  misconfigured: "Misconfigured.",
  unknown: "Availability is unknown.",
};

const AUTHORIZATION_TEXT = {
  allowed: "Allowed to run",
  approval_required: "Waiting for approval",
  denied: "Denied",
};

const STATUS_TEXT = {
  awaiting_approval: "Waiting for approval",
  denied: "Denied",
  success: "Completed",
  failure: "Failed",
  cancelled: "Cancelled",
  outcome_unknown: "Outcome unknown - it may have taken effect; check before repeating it",
};

// Capability ids are registry keys. Agent invocations and extension operations carry their
// subject in the id; everything else reads as a sentence once its separators are dropped.
export function capabilityTitle(capabilityId) {
  const id = String(capabilityId || "");
  if (!id) return "Action";
  if (id.startsWith("agent-invoke-")) return `Run agent ${id.slice("agent-invoke-".length)}`;
  if (/^extension-[0-9a-f]+$/.test(id)) return "Extension operation";
  const words = id.replaceAll(/[-_:]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export function formatCapabilityRisk(capability) {
  if (!capability) return "";
  const effect = EFFECT_TEXT[capability.effect_class] || String(capability.effect_class || "").replaceAll("_", " ");
  const rule = capability.authorization_rule === "requires_approval"
    ? "approval required"
    : capability.authorization_rule === "deny" ? "not allowed" : "";
  return [effect, rule].filter(Boolean).join(" · ");
}

export function capabilityReadinessText(capability) {
  if (!capability) return "";
  if (capability.availability !== "available") {
    return capability.unavailable_explanation || AVAILABILITY_TEXT[capability.availability] || "Unavailable.";
  }
  if (capability.readiness === "unavailable") return capability.unavailable_explanation || "Not ready to run.";
  if (capability.readiness === "degraded") return capability.unavailable_explanation || "Degraded - results may be incomplete.";
  return "";
}

export function actionStatusText(status) {
  return STATUS_TEXT[status] || String(status || "Unknown").replaceAll("_", " ");
}

export function formatActionTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function withReason(text, reason) {
  return reason ? `${text}: ${reason}` : text;
}

// One sentence per audit record kind, read from the nested backend record rather than the
// envelope, so a row says what happened instead of which table it came from.
export function describeAuditRecord(envelope) {
  const record = envelope?.record || {};
  switch (envelope?.kind) {
    case "action_proposal":
      return withReason(record.proposed_by === "model" ? "Proposed by the assistant" : "Requested by the operator", record.reason);
    case "authorization_decision":
      return record.outcome === "denied"
        ? withReason("Denied", record.reason)
        : AUTHORIZATION_TEXT[record.outcome] || withReason("Decided", record.reason);
    case "approval_record": {
      const verb = record.outcome === "approved" ? "Approved" : "Declined";
      return withReason(record.decided_by ? `${verb} by ${record.decided_by}` : verb, record.reason);
    }
    case "execution_result":
      if (record.status === "failure") return `Failed: ${record.error || "no error was reported"}`;
      if (record.status === "cancelled") return "Cancelled while running";
      return actionStatusText(record.status);
    case "action_cancellation":
      return withReason(record.cancelled_by ? `Cancelled by ${record.cancelled_by}` : "Cancelled", record.reason);
    default:
      return String(envelope?.kind || "Record").replaceAll("_", " ");
  }
}

export function auditRecordState(envelope) {
  const record = envelope?.record || {};
  switch (envelope?.kind) {
    case "authorization_decision":
      return record.outcome === "denied" ? "blocked" : record.outcome === "approval_required" ? "running" : "ready";
    case "approval_record":
      return record.outcome === "approved" ? "ready" : "blocked";
    case "execution_result":
      return executionActivityState(record);
    case "action_cancellation":
      return "cancelled";
    default:
      return "idle";
  }
}

// The audit arrives newest first. Grouping by proposal turns one action's proposal, decision,
// approval, result, and cancellation into a single timeline, read oldest to newest.
export function groupAuditRecords(records) {
  const groups = [];
  const byProposal = new Map();
  for (const record of records || []) {
    const key = record.proposal_id;
    let group = key ? byProposal.get(key) : null;
    if (!group) {
      group = { proposalId: key || "", capabilityId: record.capability_id, records: [] };
      groups.push(group);
      if (key) byProposal.set(key, group);
    }
    group.records.unshift(record);
  }
  return groups;
}

function copyState(state) {
  return {
    ...state,
    capabilities: state.capabilities ? { ...state.capabilities, capabilities: [...(state.capabilities.capabilities || [])] } : null,
    pending: state.pending ? [...state.pending] : [],
    proposeValues: { ...state.proposeValues },
    audit: state.audit ? { ...state.audit, records: [...(state.audit.records || [])] } : null,
    detail: state.detail ? { ...state.detail } : null,
  };
}

export function createActionsPanelController(handlers, render = () => undefined) {
  const state = {
    capabilities: null,
    pending: [],
    audit: null,
    detail: null,
    selectedProposalId: "",
    proposeCapabilityId: "",
    proposeValues: {},
    proposeReason: "",
    proposeError: "",
    auditLimit: 20,
    capabilitiesLoading: false,
    pendingLoading: false,
    auditLoading: false,
    detailLoading: false,
    mutationPending: false,
    capabilitiesError: "",
    pendingError: "",
    auditError: "",
    detailError: "",
    conflict: "",
    notice: "",
  };
  let capabilitiesSequence = 0;
  let pendingSequence = 0;
  let auditSequence = 0;
  let detailSequence = 0;

  function emit() {
    render(copyState(state));
  }

  async function refreshCapabilities() {
    if (!handlers.getActionCapabilities) return null;
    const request = ++capabilitiesSequence;
    state.capabilitiesLoading = true;
    state.capabilitiesError = "";
    emit();
    try {
      const payload = await handlers.getActionCapabilities();
      if (request !== capabilitiesSequence) return null;
      state.capabilities = payload;
      return payload;
    } catch (error) {
      if (request !== capabilitiesSequence) return null;
      state.capabilitiesError = errorMessage(error, "Capabilities are unavailable.");
      return null;
    } finally {
      if (request === capabilitiesSequence) {
        state.capabilitiesLoading = false;
        emit();
      }
    }
  }

  async function refreshPending() {
    if (!handlers.getPendingActions) return null;
    const request = ++pendingSequence;
    state.pendingLoading = true;
    state.pendingError = "";
    emit();
    try {
      const payload = await handlers.getPendingActions();
      if (request !== pendingSequence) return null;
      state.pending = payload?.pending || [];
      return payload;
    } catch (error) {
      if (request !== pendingSequence) return null;
      state.pendingError = errorMessage(error, "Pending approvals are unavailable.");
      return null;
    } finally {
      if (request === pendingSequence) {
        state.pendingLoading = false;
        emit();
      }
    }
  }

  async function refreshAudit(limit = state.auditLimit) {
    if (!handlers.getActionAudit) return null;
    state.auditLimit = limit;
    const request = ++auditSequence;
    state.auditLoading = true;
    state.auditError = "";
    emit();
    try {
      const payload = await handlers.getActionAudit(limit);
      if (request !== auditSequence) return null;
      state.audit = payload;
      return payload;
    } catch (error) {
      if (request !== auditSequence) return null;
      state.auditError = errorMessage(error, "The action audit is unavailable.");
      return null;
    } finally {
      if (request === auditSequence) {
        state.auditLoading = false;
        emit();
      }
    }
  }

  async function selectProposal(proposalId) {
    if (!handlers.getActionStatus) return null;
    const request = ++detailSequence;
    state.selectedProposalId = proposalId;
    state.detailLoading = true;
    state.detailError = "";
    emit();
    try {
      const payload = await handlers.getActionStatus(proposalId);
      if (request !== detailSequence) return null;
      state.detail = payload;
      return payload;
    } catch (error) {
      if (request !== detailSequence) return null;
      state.detailError = errorMessage(error, "That action is unavailable.");
      return null;
    } finally {
      if (request === detailSequence) {
        state.detailLoading = false;
        emit();
      }
    }
  }

  async function reloadAfterMutation(proposalId) {
    await refreshPending();
    await refreshAudit(state.auditLimit);
    if (proposalId) await selectProposal(proposalId);
  }

  async function mutate(proposalId, run, successNotice) {
    if (state.mutationPending) return null;
    state.mutationPending = true;
    state.conflict = "";
    state.notice = "";
    state.detailError = "";
    emit();
    try {
      const payload = await run();
      state.detail = payload && payload.proposal_id ? payload : state.detail;
      state.notice = successNotice;
      await reloadAfterMutation(proposalId);
      return payload;
    } catch (error) {
      if (isConflict(error)) {
        state.conflict = `${errorMessage(error, "That decision was not applied.")} The action was reloaded.`;
        await reloadAfterMutation(proposalId);
      } else {
        state.detailError = errorMessage(error, "That action could not be completed.");
      }
      return null;
    } finally {
      state.mutationPending = false;
      emit();
    }
  }

  async function decide(proposalId, outcome, reason = null) {
    return mutate(
      proposalId,
      () => handlers.decideAction(proposalId, outcome, reason),
      outcome === "approved" ? "Action approved." : "Action denied.",
    );
  }

  async function cancel(proposalId, confirmCancel) {
    const confirmed = await confirmCancel("Cancel this action?");
    if (!confirmed) return null;
    return mutate(proposalId, () => handlers.cancelAction(proposalId), "Action cancelled.");
  }

  function selectCapability(capabilityId) {
    const same = state.proposeCapabilityId === capabilityId;
    state.proposeCapabilityId = same ? "" : capabilityId;
    state.proposeValues = {};
    state.proposeReason = "";
    state.proposeError = "";
    emit();
  }

  function setProposeValue(name, value) {
    state.proposeValues[name] = value;
  }

  function setProposeReason(value) {
    state.proposeReason = value;
  }

  async function propose(capabilityId, actionArguments, reason) {
    const payload = await mutate(
      "",
      () => handlers.proposeAction({ capabilityId, actionArguments, reason }),
      "Action proposed.",
    );
    if (payload?.proposal_id) {
      state.proposeCapabilityId = "";
      state.proposeValues = {};
      state.proposeReason = "";
      await selectProposal(payload.proposal_id);
    }
    return payload;
  }

  function submitPropose(capability) {
    const fields = capabilityArgumentFields(capability?.input_schema);
    let actionArguments;
    try {
      actionArguments = coerceArguments(fields, state.proposeValues);
    } catch (error) {
      state.proposeError = error.message;
      emit();
      return null;
    }
    state.proposeError = "";
    return propose(capability.capability_id, actionArguments, state.proposeReason);
  }

  async function load() {
    await Promise.all([refreshCapabilities(), refreshPending(), refreshAudit(state.auditLimit)]);
  }

  function cancelPendingReads() {
    capabilitiesSequence += 1;
    pendingSequence += 1;
    auditSequence += 1;
    detailSequence += 1;
    state.capabilitiesLoading = false;
    state.pendingLoading = false;
    state.auditLoading = false;
    state.detailLoading = false;
  }

  emit();
  return {
    load,
    refreshCapabilities,
    refreshPending,
    refreshAudit,
    selectProposal,
    decide,
    cancel,
    propose,
    selectCapability,
    setProposeValue,
    setProposeReason,
    submitPropose,
    cancelPendingReads,
    snapshot: () => copyState(state),
  };
}

function appendText(parent, text, tagName = "span", className = "") {
  const node = document.createElement(tagName);
  node.textContent = text;
  if (className) node.className = className;
  parent.appendChild(node);
  return node;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function labeledValue(parent, label, value) {
  const field = document.createElement("div");
  field.className = "actions-field";
  appendText(field, label, "dt");
  appendText(field, formatValue(value), "dd");
  parent.appendChild(field);
  return field;
}

function button(text, focusKey, onClick, disabled = false) {
  const node = document.createElement("button");
  node.type = "button";
  node.textContent = text;
  node.disabled = disabled;
  if (focusKey) node.dataset.focusKey = focusKey;
  node.addEventListener("click", onClick);
  return node;
}

// Backend identifiers and raw records stay reachable for audit, but only behind an explicit
// disclosure; the visible row is written for an operator.
function detailsDisclosure(facts, raw = null) {
  const details = document.createElement("details");
  appendText(details, "Details", "summary");
  const list = document.createElement("dl");
  list.className = "actions-facts";
  for (const [label, value] of facts) {
    if (value !== null && value !== undefined && value !== "") labeledValue(list, label, value);
  }
  details.appendChild(list);
  if (raw !== null && raw !== undefined) appendText(details, JSON.stringify(raw, null, 2), "pre");
  return details;
}

function renderArguments(parent, args) {
  const entries = Object.entries(args || {});
  if (!entries.length) return;
  const list = document.createElement("dl");
  list.className = "actions-facts";
  for (const [name, value] of entries) labeledValue(list, name.replaceAll("_", " "), value);
  parent.appendChild(list);
}

function renderProposeForm(state, capability) {
  const form = document.createElement("form");
  form.className = "actions-propose";
  const fields = capabilityArgumentFields(capability.input_schema);
  for (const field of fields) {
    const label = document.createElement("label");
    appendText(label, field.required ? `${field.name} *` : field.name);
    const structured = field.type === "object" || field.type === "array";
    const control = document.createElement(structured ? "textarea" : "input");
    control.name = field.name;
    if (structured) {
      control.placeholder = "JSON";
      control.addEventListener("input", (event) => state.actions.setProposeValue(field.name, event.target.value));
    } else if (field.type === "boolean") {
      control.type = "checkbox";
      control.addEventListener("change", (event) => state.actions.setProposeValue(field.name, event.target.checked));
    } else {
      control.type = field.type === "integer" || field.type === "number" ? "number" : "text";
      control.addEventListener("input", (event) => state.actions.setProposeValue(field.name, event.target.value));
    }
    // Drafts live in controller state and are not re-emitted on input, so typing never
    // re-renders the control out from under the caret.
    const draft = state.proposeValues[field.name];
    if (field.type === "boolean") control.checked = Boolean(draft);
    else if (draft !== undefined) control.value = draft;
    control.dataset.focusKey = `propose:${capability.capability_id}:${field.name}`;
    label.appendChild(control);
    form.appendChild(label);
  }

  const reasonLabel = document.createElement("label");
  appendText(reasonLabel, "Reason *");
  const reason = document.createElement("input");
  reason.type = "text";
  reason.name = "reason";
  reason.required = true;
  reason.maxLength = 256;
  reason.value = state.proposeReason;
  reason.dataset.focusKey = `propose:${capability.capability_id}:$reason`;
  reason.addEventListener("input", (event) => state.actions.setProposeReason(event.target.value));
  reasonLabel.appendChild(reason);
  form.appendChild(reasonLabel);

  if (state.proposeError) appendText(form, state.proposeError, "p", "actions-error");

  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = proposeTriggerLabel(capability) === "Propose" ? "Propose action" : "Run action";
  submit.disabled = state.mutationPending;
  form.appendChild(submit);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!proposeEnabled(capability, state.mutationPending)) return;
    state.actions.submitPropose(capability);
  });
  return form;
}

function renderCapabilities(state) {
  const section = document.createElement("section");
  section.className = "actions-section";
  appendText(section, "Run manually", "h3");
  appendText(
    section,
    "Every registered capability, for audit and as a fallback when no dedicated control exists.",
    "p",
    "actions-help",
  );
  if (state.capabilitiesLoading) {
    appendText(section, "Loading capabilities…", "p", "actions-help");
    return section;
  }
  if (state.capabilitiesError) {
    appendText(section, state.capabilitiesError, "p", "actions-error");
    return section;
  }
  const problems = state.capabilities?.problems || [];
  if (problems.length) {
    appendText(section, "Could not load", "h4");
    for (const problem of problems) {
      const row = document.createElement("div");
      row.className = "actions-pending";
      appendText(row, `${capabilityTitle(problem.capability_id)}: ${problem.reason}`, "p", "actions-error");
      row.appendChild(detailsDisclosure([["Capability", problem.capability_id]]));
      section.appendChild(row);
    }
  }
  const capabilities = state.capabilities?.capabilities || [];
  if (!capabilities.length) {
    appendText(section, "No capabilities are registered.", "p", "actions-help");
    return section;
  }
  const list = document.createElement("ul");
  list.className = "actions-list";
  for (const capability of capabilities) {
    const item = document.createElement("li");
    const status = appendText(item, capabilityTitle(capability.capability_id), "span", "actions-status");
    status.dataset.state = capabilityActivityState(capability);
    appendText(item, formatCapabilityRisk(capability), "span", "actions-row-meta");
    const approvalText = formatCapabilityApproval(capability);
    if (approvalText) appendText(item, approvalText, "span", "actions-row-meta");
    if (!capability.executable) appendText(item, "Driven by its own control", "span", "actions-row-meta");
    const readiness = capabilityReadinessText(capability);
    if (readiness) appendText(item, readiness, "p", "actions-help");
    if (proposeEnabled(capability, false)) {
      const open = state.proposeCapabilityId === capability.capability_id;
      const trigger = button(
        open ? "Close" : proposeTriggerLabel(capability),
        `capability:${capability.capability_id}`,
        () => state.actions.selectCapability(capability.capability_id),
        state.mutationPending,
      );
      trigger.setAttribute("aria-expanded", String(open));
      item.appendChild(trigger);
      if (open) item.appendChild(renderProposeForm(state, capability));
    }
    item.appendChild(detailsDisclosure([
      ["Capability", capability.capability_id],
      ["Effect", capability.effect_class],
      ["Rule", capability.authorization_rule],
      ["Handled by", capability.execution_owner],
    ]));
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

function renderPending(state) {
  const section = document.createElement("section");
  section.className = "actions-section";
  appendText(section, "Awaiting approval", "h3");
  if (state.pendingLoading) {
    appendText(section, "Loading pending approvals…", "p", "actions-help");
    return section;
  }
  if (state.pendingError) {
    appendText(section, state.pendingError, "p", "actions-error");
    return section;
  }
  if (!state.pending.length) {
    appendText(section, "No actions are awaiting approval.", "p", "actions-help");
    return section;
  }
  for (const pending of state.pending) {
    const row = document.createElement("div");
    row.className = "actions-pending";
    appendText(row, capabilityTitle(pending.capability_id), "strong");
    appendText(row, pending.reason, "p", "actions-help");
    renderArguments(row, pending.arguments);
    appendText(row, `Expires ${formatActionTime(pending.expires_at)}`, "p", "actions-row-meta");

    const buttons = document.createElement("div");
    buttons.className = "actions-buttons";
    const enabled = actionApprovalEnabled(pending, state.mutationPending);
    for (const [label, outcome] of [["Approve", "approved"], ["Deny", "denied"]]) {
      buttons.appendChild(button(label, `pending:${pending.proposal_id}:${outcome}`, () => state.actions.decide(pending.proposal_id, outcome), !enabled));
    }
    buttons.appendChild(button("Cancel", `pending:${pending.proposal_id}:cancel`, () => state.actions.cancel(pending.proposal_id), !enabled));
    buttons.appendChild(button("Status", `pending:${pending.proposal_id}:status`, () => state.actions.selectProposal(pending.proposal_id), state.mutationPending));
    row.appendChild(buttons);
    row.appendChild(detailsDisclosure([
      ["Capability", pending.capability_id],
      ["Proposal", pending.proposal_id],
      ["Approval", pending.approval_id],
      ["Expires at", pending.expires_at],
    ], pending.arguments));
    section.appendChild(row);
  }
  return section;
}

function renderDetail(state) {
  const section = document.createElement("section");
  section.className = "actions-section";
  appendText(section, "Execution status", "h3");
  if (state.detailLoading) {
    appendText(section, "Loading action…", "p", "actions-help");
    return section;
  }
  if (state.detailError) {
    appendText(section, state.detailError, "p", "actions-error");
    return section;
  }
  if (!state.detail) {
    appendText(section, "Select an action to see its status.", "p", "actions-help");
    return section;
  }
  const detail = state.detail;
  appendText(section, capabilityTitle(detail.capability_id), "strong");
  const status = appendText(section, actionStatusText(detail.status), "p", "actions-status");
  status.dataset.state = executionActivityState(detail.execution || { status: detail.status });
  const facts = document.createElement("dl");
  facts.className = "actions-facts";
  labeledValue(facts, "Reason", detail.reason);
  labeledValue(facts, "Decision", AUTHORIZATION_TEXT[detail.outcome] || detail.outcome);
  if (detail.expires_at) labeledValue(facts, "Expires", formatActionTime(detail.expires_at));
  const execution = detail.execution;
  if (execution) {
    if (execution.error) labeledValue(facts, "Error", execution.error);
    if (execution.started_at) labeledValue(facts, "Started", formatActionTime(execution.started_at));
    if (execution.completed_at) labeledValue(facts, "Finished", formatActionTime(execution.completed_at));
  }
  section.appendChild(facts);
  renderArguments(section, detail.arguments);
  section.appendChild(detailsDisclosure([
    ["Capability", detail.capability_id],
    ["Proposal", detail.proposal_id],
    ["Approval", detail.approval_id],
    ["Status", detail.status],
    ["Outcome", detail.outcome],
  ], execution || null));
  return section;
}

function renderAudit(state) {
  const section = document.createElement("section");
  section.className = "actions-section";
  appendText(section, "Audit", "h3");

  const form = document.createElement("form");
  form.className = "actions-filters";
  const label = document.createElement("label");
  appendText(label, "Records");
  const select = document.createElement("select");
  select.name = "limit";
  select.dataset.focusKey = "audit:limit";
  for (const limit of AUDIT_LIMITS) {
    const choice = document.createElement("option");
    choice.value = String(limit);
    choice.textContent = String(limit);
    if (limit === state.auditLimit) choice.selected = true;
    select.appendChild(choice);
  }
  label.appendChild(select);
  form.appendChild(label);
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = "Refresh";
  submit.dataset.focusKey = "audit:refresh";
  form.appendChild(submit);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    state.actions.refreshAudit(Number(select.value));
  });
  section.appendChild(form);

  if (state.auditLoading) {
    appendText(section, "Loading audit…", "p", "actions-help");
    return section;
  }
  if (state.auditError) {
    appendText(section, state.auditError, "p", "actions-error");
    return section;
  }
  const records = state.audit?.records || [];
  if (!records.length) {
    appendText(section, "No action evidence has been recorded.", "p", "actions-help");
    return section;
  }
  const list = document.createElement("ul");
  list.className = "actions-list";
  for (const group of groupAuditRecords(records)) {
    const item = document.createElement("li");
    appendText(item, capabilityTitle(group.capabilityId), "strong");
    const steps = document.createElement("ol");
    steps.className = "actions-audit-steps";
    for (const record of group.records) {
      const step = appendText(steps, `${formatActionTime(record.recorded_at)} · ${describeAuditRecord(record)}`, "li", "actions-status");
      step.dataset.state = auditRecordState(record);
    }
    item.appendChild(steps);
    if (group.proposalId) {
      item.appendChild(button("Status", `audit:${group.proposalId}:status`, () => state.actions.selectProposal(group.proposalId), state.mutationPending));
    }
    item.appendChild(detailsDisclosure([
      ["Capability", group.capabilityId],
      ["Proposal", group.proposalId],
    ], group.records));
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

function renderPanel(keeper, state, actions) {
  const view = { ...state, actions };
  const header = document.createElement("div");
  header.className = "actions-panel-header";
  const heading = appendText(header, "Actions", "h2");
  heading.tabIndex = -1;

  const messages = document.createElement("div");
  messages.setAttribute("aria-live", "polite");
  for (const message of [state.conflict, state.notice]) {
    if (message) {
      appendText(messages, message, "p", message === state.notice ? "actions-notice" : "actions-error");
    }
  }

  keeper.render(
    header,
    messages,
    renderPending(view),
    renderDetail(view),
    renderAudit(view),
    renderCapabilities(view),
  );
}

export function createActionsPanel(container, handlers, options = {}) {
  let open = false;
  const keeper = createRenderStateKeeper(container);
  const confirmCancel = options.confirmCancel || ((message) => window.confirm(message));
  let controller;
  const actions = {
    close: () => close(),
    refreshAudit: (limit) => controller.refreshAudit(limit),
    selectProposal: (proposalId) => controller.selectProposal(proposalId),
    decide: (proposalId, outcome) => controller.decide(proposalId, outcome),
    cancel: (proposalId) => controller.cancel(proposalId, confirmCancel),
    selectCapability: (capabilityId) => controller.selectCapability(capabilityId),
    setProposeValue: (name, value) => controller.setProposeValue(name, value),
    setProposeReason: (value) => controller.setProposeReason(value),
    submitPropose: (capability) => controller.submitPropose(capability),
  };
  controller = createActionsPanelController(handlers, (state) => {
    if (open) renderPanel(keeper, state, actions);
  });

  async function show() {
    open = true;
    container.hidden = false;
    renderPanel(keeper, controller.snapshot(), actions);
    await controller.load();
    keeper.release();
    container.querySelector("h2")?.focus();
  }

  function close() {
    if (!open) return;
    open = false;
    controller.cancelPendingReads();
    keeper.retain();
    container.hidden = true;
    container.replaceChildren();
    options.onClose?.();
  }

  return { open: show, close, isOpen: () => open, controller };
}
