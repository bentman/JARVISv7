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
  return "running";
}

export function capabilityActivityState(capability) {
  if (!capability) return "idle";
  if (capability.availability !== "available") return "blocked";
  if (capability.readiness === "degraded") return "degraded";
  if (capability.readiness === "unavailable") return "blocked";
  return "ready";
}

export function formatCapabilityRisk(capability) {
  if (!capability) return "";
  const rule = capability.authorization_rule === "requires_approval" ? "approval required" : capability.authorization_rule;
  return `${capability.effect_class} · ${rule}`;
}

export function formatCapabilityApproval(capability) {
  if (!capability) return "";
  // A turn_boundary capability is proposed and executed inside a conversation turn, so the
  // operator surface can only report it, never drive it.
  return capability.approval_mode === "turn_boundary"
    ? "approved in conversation"
    : "approved here";
}

function copyState(state) {
  return {
    ...state,
    capabilities: state.capabilities ? { ...state.capabilities, capabilities: [...(state.capabilities.capabilities || [])] } : null,
    pending: state.pending ? [...state.pending] : [],
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
    const confirmed = await confirmCancel(`Cancel action ${proposalId}?`);
    if (!confirmed) return null;
    return mutate(proposalId, () => handlers.cancelAction(proposalId), "Action cancelled.");
  }

  async function propose(capabilityId, actionArguments, reason) {
    return mutate(
      "",
      () => handlers.proposeAction({ capabilityId, actionArguments, reason }),
      "Action proposed.",
    );
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

function renderCapabilities(state) {
  const section = document.createElement("section");
  section.className = "actions-section";
  appendText(section, "Capabilities", "h3");
  if (state.capabilitiesLoading) {
    appendText(section, "Loading capabilities…", "p", "actions-help");
    return section;
  }
  if (state.capabilitiesError) {
    appendText(section, state.capabilitiesError, "p", "actions-error");
    return section;
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
    const status = appendText(item, capability.capability_id, "span", "actions-status");
    status.dataset.state = capabilityActivityState(capability);
    appendText(item, formatCapabilityRisk(capability), "span", "actions-row-meta");
    appendText(item, formatCapabilityApproval(capability), "span", "actions-row-meta");
    if (!capability.executable) {
      appendText(item, "No application-owned handler is wired.", "span", "actions-row-meta");
    }
    if (capability.availability !== "available" && capability.unavailable_explanation) {
      appendText(item, capability.unavailable_explanation, "p", "actions-help");
    }
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
    appendText(row, pending.capability_id, "strong");
    appendText(row, pending.reason, "p", "actions-help");
    const facts = document.createElement("dl");
    facts.className = "actions-facts";
    labeledValue(facts, "Proposal", pending.proposal_id);
    labeledValue(facts, "Expires", pending.expires_at);
    labeledValue(facts, "Arguments", JSON.stringify(pending.arguments || {}));
    row.appendChild(facts);

    const buttons = document.createElement("div");
    buttons.className = "actions-buttons";
    const enabled = actionApprovalEnabled(pending, state.mutationPending);
    for (const [label, outcome] of [["Approve", "approved"], ["Deny", "denied"]]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.disabled = !enabled;
      button.addEventListener("click", () => state.actions.decide(pending.proposal_id, outcome));
      buttons.appendChild(button);
    }
    const cancelButton = document.createElement("button");
    cancelButton.type = "button";
    cancelButton.textContent = "Cancel";
    cancelButton.disabled = !enabled;
    cancelButton.addEventListener("click", () => state.actions.cancel(pending.proposal_id));
    buttons.appendChild(cancelButton);

    const inspect = document.createElement("button");
    inspect.type = "button";
    inspect.textContent = "Status";
    inspect.disabled = state.mutationPending;
    inspect.addEventListener("click", () => state.actions.selectProposal(pending.proposal_id));
    buttons.appendChild(inspect);

    row.appendChild(buttons);
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
  const status = appendText(section, formatValue(detail.status), "p", "actions-status");
  status.dataset.state = executionActivityState(detail.execution || { status: detail.status });
  const facts = document.createElement("dl");
  facts.className = "actions-facts";
  labeledValue(facts, "Proposal", detail.proposal_id);
  labeledValue(facts, "Capability", detail.capability_id);
  labeledValue(facts, "Outcome", detail.outcome);
  labeledValue(facts, "Reason", detail.reason);
  labeledValue(facts, "Approval", detail.approval_id);
  labeledValue(facts, "Expires", detail.expires_at);
  section.appendChild(facts);
  if (detail.execution) {
    const execution = document.createElement("details");
    appendText(execution, "Execution result", "summary");
    appendText(execution, JSON.stringify(detail.execution), "p");
    section.appendChild(execution);
  }
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
  for (const record of records) {
    const item = document.createElement("li");
    appendText(item, `${record.kind} · ${record.capability_id}`, "strong");
    appendText(item, formatValue(record.recorded_at), "span", "actions-row-meta");
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

function renderPanel(container, state, actions) {
  const view = { ...state, actions };
  const header = document.createElement("div");
  header.className = "actions-panel-header";
  const heading = appendText(header, "Actions", "h2");
  heading.tabIndex = -1;
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Close";
  close.addEventListener("click", () => actions.close());
  header.appendChild(close);

  const messages = document.createElement("div");
  messages.setAttribute("aria-live", "polite");
  for (const message of [state.conflict, state.notice]) {
    if (message) {
      appendText(messages, message, "p", message === state.notice ? "actions-notice" : "actions-error");
    }
  }

  container.replaceChildren(
    header,
    messages,
    renderPending(view),
    renderDetail(view),
    renderCapabilities(view),
    renderAudit(view),
  );
}

export function createActionsPanel(container, handlers, options = {}) {
  let open = false;
  const confirmCancel = options.confirmCancel || ((message) => window.confirm(message));
  let controller;
  const actions = {
    close: () => close(),
    refreshAudit: (limit) => controller.refreshAudit(limit),
    selectProposal: (proposalId) => controller.selectProposal(proposalId),
    decide: (proposalId, outcome) => controller.decide(proposalId, outcome),
    cancel: (proposalId) => controller.cancel(proposalId, confirmCancel),
  };
  controller = createActionsPanelController(handlers, (state) => {
    if (open) renderPanel(container, state, actions);
  });

  async function show() {
    open = true;
    container.hidden = false;
    renderPanel(container, controller.snapshot(), actions);
    await controller.load();
    container.querySelector("h2")?.focus();
  }

  function close() {
    if (!open) return;
    open = false;
    controller.cancelPendingReads();
    container.hidden = true;
    container.replaceChildren();
    options.onClose?.();
  }

  return { open: show, close, isOpen: () => open, controller };
}
