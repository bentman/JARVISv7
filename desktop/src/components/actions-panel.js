import { confirmDestructive } from "./ui/confirm.js";
import { appendText, button, buttonRow, details, facts, field, option } from "./ui/dom.js";
import { errorMessage, formatTime, humanize, isConflict, statusText } from "./ui/format.js";
import { createPanelLifecycle, messageRegion, renderPanelHeader, section, sectionState } from "./ui/panel.js";
import { VERB } from "./ui/vocabulary.js";

const AUDIT_LIMITS = [10, 20, 50, 100];

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
  return statusText(status);
}

export function formatActionTime(value) {
  return formatTime(value);
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

function renderArguments(parent, args) {
  const entries = Object.entries(args || {});
  if (!entries.length) return;
  parent.appendChild(facts(entries.map(([name, value]) => [humanize(name), value])));
}

function renderProposeForm(state, capability) {
  const form = document.createElement("form");
  form.className = "actions-propose";
  const fields = capabilityArgumentFields(capability.input_schema);
  for (const argument of fields) {
    const structured = argument.type === "object" || argument.type === "array";
    const control = document.createElement(structured ? "textarea" : "input");
    control.name = argument.name;
    if (structured) {
      control.placeholder = "JSON";
      control.addEventListener("input", (event) => state.actions.setProposeValue(argument.name, event.target.value));
    } else if (argument.type === "boolean") {
      control.type = "checkbox";
      control.addEventListener("change", (event) => state.actions.setProposeValue(argument.name, event.target.checked));
    } else {
      control.type = argument.type === "integer" || argument.type === "number" ? "number" : "text";
      control.addEventListener("input", (event) => state.actions.setProposeValue(argument.name, event.target.value));
    }
    // Drafts live in controller state and are not re-emitted on input, so typing never
    // re-renders the control out from under the caret.
    const draft = state.proposeValues[argument.name];
    if (argument.type === "boolean") control.checked = Boolean(draft);
    else if (draft !== undefined) control.value = draft;
    control.dataset.focusKey = `propose:${capability.capability_id}:${argument.name}`;
    form.appendChild(field(argument.required ? `${humanize(argument.name)} *` : humanize(argument.name), control));
  }

  const reason = document.createElement("input");
  reason.type = "text";
  reason.name = "reason";
  reason.required = true;
  reason.maxLength = 256;
  reason.value = state.proposeReason;
  reason.dataset.focusKey = `propose:${capability.capability_id}:$reason`;
  reason.addEventListener("input", (event) => state.actions.setProposeReason(event.target.value));
  form.appendChild(field("Reason *", reason));

  if (state.proposeError) appendText(form, state.proposeError, "p", "panel-error");

  form.appendChild(button(proposeTriggerLabel(capability) === "Propose" ? "Propose action" : "Run action", {
    type: "submit",
    disabled: state.mutationPending,
  }));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!proposeEnabled(capability, state.mutationPending)) return;
    state.actions.submitPropose(capability);
  });
  return form;
}

function renderCapabilities(state) {
  const node = section("Run manually");
  appendText(node, "Every registered action, for audit and as a fallback when no dedicated control exists.", "p", "panel-help");
  if (sectionState(node, { loading: state.capabilitiesLoading, error: state.capabilitiesError, thing: "actions" })) return node;
  const problems = state.capabilities?.problems || [];
  if (problems.length) {
    appendText(node, "Could not load", "h4");
    for (const problem of problems) {
      const row = document.createElement("div");
      row.className = "actions-pending";
      appendText(row, `${capabilityTitle(problem.capability_id)}: ${problem.reason}`, "p", "panel-error");
      row.appendChild(details([["Capability", problem.capability_id]]));
      node.appendChild(row);
    }
  }
  const capabilities = state.capabilities?.capabilities || [];
  if (sectionState(node, { empty: !capabilities.length, thing: "actions" })) return node;
  const list = document.createElement("ul");
  list.className = "panel-list";
  for (const capability of capabilities) {
    const item = document.createElement("li");
    const status = appendText(item, capabilityTitle(capability.capability_id), "span", "actions-status");
    status.dataset.state = capabilityActivityState(capability);
    appendText(item, formatCapabilityRisk(capability), "span", "panel-help");
    const approvalText = formatCapabilityApproval(capability);
    if (approvalText) appendText(item, approvalText, "span", "panel-help");
    if (!capability.executable) appendText(item, "Driven by its own control", "span", "panel-help");
    const readiness = capabilityReadinessText(capability);
    if (readiness) appendText(item, readiness, "p", "panel-help");
    if (proposeEnabled(capability, false)) {
      const open = state.proposeCapabilityId === capability.capability_id;
      const trigger = button(open ? "Close" : proposeTriggerLabel(capability), {
        focusKey: `capability:${capability.capability_id}`,
        onClick: () => state.actions.selectCapability(capability.capability_id),
        disabled: state.mutationPending,
      });
      trigger.setAttribute("aria-expanded", String(open));
      item.appendChild(buttonRow(trigger));
      if (open) item.appendChild(renderProposeForm(state, capability));
    }
    item.appendChild(details([
      ["Capability", capability.capability_id],
      ["Effect", capability.effect_class],
      ["Rule", capability.authorization_rule],
      ["Handled by", capability.execution_owner],
    ]));
    list.appendChild(item);
  }
  node.appendChild(list);
  return node;
}

function renderPending(state) {
  const node = section("Waiting for approval");
  if (sectionState(node, { loading: state.pendingLoading, error: state.pendingError, thing: "approval requests" })) return node;
  if (!state.pending.length) {
    appendText(node, "Nothing is waiting for your approval.", "p", "panel-help");
    return node;
  }
  for (const pending of state.pending) {
    const row = document.createElement("div");
    row.className = "actions-pending";
    const fromConversation = pending.origin === "conversation";
    appendText(row, pending.label || capabilityTitle(pending.capability_id), "strong");
    appendText(row, fromConversation ? `Asked in the conversation · ${pending.reason}` : pending.reason, "p", "panel-help");
    renderArguments(row, pending.arguments);
    if (pending.expires_at) appendText(row, `Expires ${formatActionTime(pending.expires_at)}`, "p", "panel-help");

    const enabled = actionApprovalEnabled(pending, state.mutationPending);
    row.appendChild(buttonRow(
      button(VERB.approve, {
        variant: "primary",
        focusKey: `pending:${pending.proposal_id}:approved`,
        onClick: () => state.actions.decide(pending.proposal_id, "approved"),
        disabled: !enabled,
      }),
      button(VERB.decline, {
        focusKey: `pending:${pending.proposal_id}:denied`,
        onClick: () => state.actions.decide(pending.proposal_id, "denied"),
        disabled: !enabled,
      }),
      fromConversation ? null : button("Withdraw", {
        variant: "danger",
        focusKey: `pending:${pending.proposal_id}:cancel`,
        onClick: () => state.actions.cancel(pending.proposal_id),
        disabled: !enabled,
      }),
      button("Status", {
        variant: "ghost",
        focusKey: `pending:${pending.proposal_id}:status`,
        onClick: () => state.actions.selectProposal(pending.proposal_id),
        disabled: state.mutationPending,
      }),
    ));
    row.appendChild(details([
      ["Capability", pending.capability_id],
      ["Proposal", pending.proposal_id],
      ["Approval", pending.approval_id],
      ["Expires at", pending.expires_at],
    ], pending.arguments));
    node.appendChild(row);
  }
  return node;
}

function renderDetail(state) {
  const node = section("Action status");
  if (sectionState(node, { loading: state.detailLoading, error: state.detailError, thing: "the action" })) return node;
  if (!state.detail) {
    appendText(node, "Select an action to see its status.", "p", "panel-help");
    return node;
  }
  const detail = state.detail;
  appendText(node, capabilityTitle(detail.capability_id), "strong");
  const status = appendText(node, actionStatusText(detail.status), "p", "actions-status");
  status.dataset.state = executionActivityState(detail.execution || { status: detail.status });
  const entries = [["Reason", detail.reason], ["Decision", AUTHORIZATION_TEXT[detail.outcome] || detail.outcome]];
  if (detail.expires_at) entries.push(["Expires", formatActionTime(detail.expires_at)]);
  const execution = detail.execution;
  if (execution) {
    if (execution.error) entries.push(["Error", execution.error]);
    if (execution.started_at) entries.push(["Started", formatActionTime(execution.started_at)]);
    if (execution.completed_at) entries.push(["Finished", formatActionTime(execution.completed_at)]);
  }
  node.appendChild(facts(entries));
  renderArguments(node, detail.arguments);
  node.appendChild(details([
    ["Capability", detail.capability_id],
    ["Proposal", detail.proposal_id],
    ["Approval", detail.approval_id],
    ["Status", detail.status],
    ["Outcome", detail.outcome],
  ], execution || null));
  return node;
}

function renderAudit(state) {
  const node = section("Audit");

  const form = document.createElement("form");
  form.className = "actions-filters";
  const select = document.createElement("select");
  select.name = "limit";
  select.dataset.focusKey = "audit:limit";
  for (const limit of AUDIT_LIMITS) select.appendChild(option(String(limit), String(limit), limit === state.auditLimit));
  form.append(field("Records", select), buttonRow(button(VERB.refresh, { type: "submit", focusKey: "audit:refresh" })));
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    state.actions.refreshAudit(Number(select.value));
  });
  node.appendChild(form);

  if (sectionState(node, { loading: state.auditLoading, error: state.auditError, thing: "the audit" })) return node;
  const records = state.audit?.records || [];
  if (!records.length) {
    appendText(node, "No action evidence has been recorded.", "p", "panel-help");
    return node;
  }
  const list = document.createElement("ul");
  list.className = "panel-list";
  for (const group of groupAuditRecords(records)) {
    const item = document.createElement("li");
    appendText(item, capabilityTitle(group.capabilityId), "strong");
    const steps = document.createElement("ol");
    steps.className = "audit-steps";
    for (const record of group.records) {
      const step = appendText(steps, `${formatActionTime(record.recorded_at)} · ${describeAuditRecord(record)}`, "li", "actions-status");
      step.dataset.state = auditRecordState(record);
    }
    item.appendChild(steps);
    if (group.proposalId) {
      item.appendChild(buttonRow(button("Status", {
        variant: "ghost",
        focusKey: `audit:${group.proposalId}:status`,
        onClick: () => state.actions.selectProposal(group.proposalId),
        disabled: state.mutationPending,
      })));
    }
    item.appendChild(details([["Capability", group.capabilityId], ["Proposal", group.proposalId]], group.records));
    list.appendChild(item);
  }
  node.appendChild(list);
  return node;
}

function renderPanel(state) {
  return [
    renderPanelHeader("Actions"),
    messageRegion({ notice: state.notice, error: state.conflict }),
    renderPending(state),
    renderDetail(state),
    renderAudit(state),
    renderCapabilities(state),
  ];
}

export function createActionsPanel(container, handlers, options = {}) {
  const confirmCancel = options.confirmCancel || confirmDestructive;
  let controller;
  const actions = {
    refreshAudit: (limit) => controller.refreshAudit(limit),
    selectProposal: (proposalId) => controller.selectProposal(proposalId),
    decide: (proposalId, outcome) => controller.decide(proposalId, outcome),
    cancel: (proposalId) => controller.cancel(proposalId, confirmCancel),
    selectCapability: (capabilityId) => controller.selectCapability(capabilityId),
    setProposeValue: (name, value) => controller.setProposeValue(name, value),
    setProposeReason: (value) => controller.setProposeReason(value),
    submitPropose: (capability) => controller.submitPropose(capability),
  };
  const lifecycle = createPanelLifecycle(container, {
    load: () => controller.load(),
    render: (state) => renderPanel({ ...state, actions }),
    cancelPendingReads: () => controller.cancelPendingReads(),
    onClose: options.onClose,
  });
  controller = createActionsPanelController(handlers, lifecycle.draw);
  return { open: lifecycle.open, close: lifecycle.close, isOpen: lifecycle.isOpen, controller };
}
