const MEMORY_KINDS = [
  "unclassified",
  "user_preference",
  "personal_fact",
  "project_fact",
  "decision",
  "commitment",
  "relationship",
  "summary",
];

const MEMORY_STATES = [
  "pending_review",
  "active",
  "disputed",
  "superseded",
  "expired",
  "forgotten",
];

function errorMessage(error, fallback) {
  return error?.detail?.message || error?.message || fallback;
}

function isConflict(error) {
  return error?.status === 409 || error?.detail?.error === "conflict";
}

function copyState(state) {
  return {
    ...state,
    filters: { ...state.filters },
    list: state.list ? { ...state.list, records: [...(state.list.records || [])] } : null,
  };
}

export function createMemoryPanelController(handlers, render = () => undefined) {
  const state = {
    filters: { lifecycleState: null, kind: null, query: null, offset: 0, limit: 20 },
    policy: null,
    curation: null,
    list: null,
    detail: null,
    correction: null,
    listLoading: false,
    detailLoading: false,
    mutationPending: false,
    policyPending: false,
    listError: "",
    detailError: "",
    policyError: "",
    curationError: "",
    conflict: "",
    notice: "",
  };
  let listSequence = 0;
  let detailSequence = 0;

  function emit() {
    render(copyState(state));
  }

  async function refreshPolicy() {
    try {
      state.policy = await handlers.getMemoryPolicy();
      state.policyError = "";
    } catch (error) {
      state.policyError = errorMessage(error, "Memory policy is unavailable.");
    }
    emit();
    return state.policy;
  }

  async function refreshCuration() {
    try {
      state.curation = await handlers.getMemoryCurationStatus();
      state.curationError = "";
    } catch (error) {
      state.curationError = errorMessage(error, "Memory curation status is unavailable.");
    }
    emit();
    return state.curation;
  }

  async function refreshList(filters = {}) {
    const request = ++listSequence;
    state.filters = { ...state.filters, ...filters };
    state.listLoading = true;
    state.listError = "";
    emit();
    try {
      const payload = await handlers.listMemories(state.filters);
      if (request !== listSequence) return null;
      state.list = payload;
      state.listError = "";
      return payload;
    } catch (error) {
      if (request !== listSequence) return null;
      state.listError = errorMessage(error, "Memory records are unavailable.");
      return null;
    } finally {
      if (request === listSequence) {
        state.listLoading = false;
        emit();
      }
    }
  }

  async function selectMemory(factId) {
    const request = ++detailSequence;
    state.detailLoading = true;
    state.detailError = "";
    emit();
    try {
      const payload = await handlers.getMemoryDetail(factId);
      if (request !== detailSequence) return null;
      state.detail = payload;
      state.detailError = "";
      return payload;
    } catch (error) {
      if (request !== detailSequence) return null;
      state.detailError = errorMessage(error, "Memory detail is unavailable.");
      return null;
    } finally {
      if (request === detailSequence) {
        state.detailLoading = false;
        emit();
      }
    }
  }

  async function updatePolicy(enabled) {
    if (state.policyPending || !state.policy) return null;
    state.policyPending = true;
    state.policyError = "";
    state.conflict = "";
    state.notice = "";
    emit();
    try {
      state.policy = await handlers.updateMemoryPolicy(enabled, state.policy.revision);
      state.notice = `Automatic retention ${state.policy.automatic_curation_enabled ? "enabled" : "disabled"}.`;
      await refreshCuration();
      return state.policy;
    } catch (error) {
      if (isConflict(error)) {
        state.conflict = "The memory policy changed elsewhere. Current backend policy was reloaded.";
        await refreshPolicy();
        await refreshCuration();
      } else {
        state.policyError = errorMessage(error, "Memory policy could not be updated.");
      }
      return null;
    } finally {
      state.policyPending = false;
      emit();
    }
  }

  async function reloadAfterMutation(factId) {
    await Promise.all([selectMemory(factId), refreshList()]);
  }

  async function mutate(action, payload = {}) {
    const current = state.detail?.record;
    if (state.mutationPending || !current) return null;
    const operation = handlers[`${action}Memory`];
    if (!operation) return null;
    state.mutationPending = true;
    state.detailError = "";
    state.conflict = "";
    state.notice = "";
    emit();
    try {
      let result;
      if (action === "correct") {
        result = await operation(
          current.fact_id,
          current.revision,
          payload.replacementText,
          payload.replacementValue || null,
          payload.reason || null,
        );
        state.correction = result;
        state.notice = "Correction saved. Original and replacement records were reloaded.";
        await reloadAfterMutation(result.replacement.fact_id);
      } else {
        result = await operation(current.fact_id, current.revision, payload.reason || null);
        state.notice =
          action === "forget"
            ? "Memory record forgotten."
            : action === "confirm"
              ? "Memory confirmed."
              : "Memory disputed.";
        await reloadAfterMutation(current.fact_id);
      }
      return result;
    } catch (error) {
      if (isConflict(error)) {
        state.conflict = "This memory changed elsewhere. Current backend detail was reloaded; your attempted change was not applied.";
        await reloadAfterMutation(current.fact_id);
      } else {
        state.detailError = errorMessage(error, `Memory ${action} failed. The displayed record was retained.`);
      }
      return null;
    } finally {
      state.mutationPending = false;
      emit();
    }
  }

  async function forget(confirmForget) {
    const current = state.detail?.record;
    if (!current) return null;
    const confirmed = await confirmForget(
      "Forget this semantic memory? It will stop being used, but source conversation and session artifacts are separate and are not erased by this operation.",
    );
    if (!confirmed) return null;
    return mutate("forget");
  }

  async function load() {
    state.conflict = "";
    state.notice = "";
    await Promise.all([refreshPolicy(), refreshCuration(), refreshList()]);
  }

  function cancelPendingReads() {
    listSequence += 1;
    detailSequence += 1;
    state.listLoading = false;
    state.detailLoading = false;
  }

  emit();
  return {
    load,
    refreshPolicy,
    refreshCuration,
    refreshList,
    selectMemory,
    updatePolicy,
    confirm: (reason = null) => mutate("confirm", { reason }),
    correct: (payload) => mutate("correct", payload),
    dispute: (reason = null) => mutate("dispute", { reason }),
    forget,
    cancelPendingReads,
    snapshot: () => copyState(state),
  };
}

function appendText(parent, text, tagName = "span", className = "") {
  const element = document.createElement(tagName);
  element.textContent = text;
  if (className) element.className = className;
  parent.appendChild(element);
  return element;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

export function memoryActionsEnabled(record, mutationPending) {
  return Boolean(record) && !mutationPending;
}

export function curationActivityState(status) {
  if (!status.service_available || !status.processor_available || status.retry_blocked) return "blocked";
  if (status.degraded) return "degraded";
  if (status.drain_active || status.current_job_id || Number(status.processing_count) > 0) return "running";
  return "idle";
}

function labeledValue(parent, label, value) {
  const row = document.createElement("div");
  row.className = "memory-field";
  appendText(row, label, "dt");
  appendText(row, formatValue(value), "dd");
  parent.appendChild(row);
}

function option(select, value, label) {
  const item = document.createElement("option");
  item.value = value;
  item.textContent = label;
  select.appendChild(item);
}

function renderCuration(state) {
  const section = document.createElement("section");
  section.className = "memory-section";
  appendText(section, "Policy & curation", "h3");

  if (state.policy) {
    const label = document.createElement("label");
    label.className = "memory-policy-toggle";
    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.checked = Boolean(state.policy.automatic_curation_enabled);
    toggle.disabled = state.policyPending;
    toggle.addEventListener("change", () => state.actions.updatePolicy(toggle.checked));
    appendText(label, "Automatic retention (opt-in)");
    label.prepend(toggle);
    section.appendChild(label);
    appendText(
      section,
      "Model-proposed memories remain application-governed. Enabling this allows automatic review; it does not bypass lifecycle controls.",
      "p",
      "memory-help",
    );
  } else if (!state.policyError) {
    appendText(section, "Loading memory policy…", "p", "memory-help");
  }

  const status = state.curation;
  if (status) {
    const statusName = curationActivityState(status);
    const badge = appendText(section, statusName, "strong", "memory-status");
    badge.dataset.state = statusName;
    const facts = document.createElement("dl");
    facts.className = "memory-facts";
    labeledValue(facts, "Pending", status.pending_count);
    labeledValue(facts, "Processing", status.processing_count);
    labeledValue(facts, "Failed", status.failed_count);
    labeledValue(facts, "Current job", status.current_job_id);
    labeledValue(facts, "Reason", status.degraded_reason || status.last_result_reason);
    labeledValue(facts, "Updated", status.last_updated_at);
    section.appendChild(facts);
    if (status.recent_jobs?.length) {
      const jobs = document.createElement("details");
      const summary = document.createElement("summary");
      summary.textContent = `Recent jobs (${status.jobs_returned})`;
      jobs.appendChild(summary);
      for (const job of status.recent_jobs) {
        const row = document.createElement("p");
        row.textContent = `${job.status} · ${job.last_reason || job.blocked_reason || "no reason"} · enqueued ${job.enqueued_at} · started ${formatValue(job.started_at)} · completed ${formatValue(job.completed_at)} · updated ${job.updated_at}`;
        jobs.appendChild(row);
      }
      section.appendChild(jobs);
    }
  } else if (!state.curationError) {
    appendText(section, "Loading curation status…", "p", "memory-help");
  }
  return section;
}

function renderFilters(state) {
  const form = document.createElement("form");
  form.className = "memory-filters";
  const searchLabel = document.createElement("label");
  searchLabel.textContent = "Search";
  const search = document.createElement("input");
  search.type = "search";
  search.maxLength = 240;
  search.value = state.filters.query || "";
  searchLabel.appendChild(search);

  const kindLabel = document.createElement("label");
  kindLabel.textContent = "Kind";
  const kind = document.createElement("select");
  option(kind, "", "Default kinds");
  for (const value of MEMORY_KINDS) option(kind, value, value.replaceAll("_", " "));
  kind.value = state.filters.kind || "";
  kindLabel.appendChild(kind);

  const lifecycleLabel = document.createElement("label");
  lifecycleLabel.textContent = "Lifecycle";
  const lifecycle = document.createElement("select");
  option(lifecycle, "", "Active + review");
  for (const value of MEMORY_STATES) option(lifecycle, value, value.replaceAll("_", " "));
  lifecycle.value = state.filters.lifecycleState || "";
  lifecycleLabel.appendChild(lifecycle);

  const apply = document.createElement("button");
  apply.type = "submit";
  apply.textContent = "Apply";
  apply.disabled = state.listLoading;
  form.append(searchLabel, kindLabel, lifecycleLabel, apply);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    state.actions.refreshList({
      query: search.value.trim() || null,
      kind: kind.value || null,
      lifecycleState: lifecycle.value || null,
      offset: 0,
    });
  });
  return form;
}

function renderList(state) {
  const section = document.createElement("section");
  section.className = "memory-section";
  appendText(section, "Records", "h3");
  section.appendChild(renderFilters(state));
  if (state.listLoading) appendText(section, "Loading records…", "p", "memory-help");
  if (state.listError) appendText(section, state.listError, "p", "memory-error");
  const records = state.list?.records || [];
  if (!state.listLoading && !state.listError && records.length === 0) {
    appendText(section, "No memories match these bounded filters.", "p", "memory-help");
  }
  const list = document.createElement("div");
  list.className = "memory-list";
  for (const record of records) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "memory-row";
    button.dataset.state = record.lifecycle_state;
    button.setAttribute("aria-pressed", state.detail?.record?.fact_id === record.fact_id ? "true" : "false");
    appendText(button, record.text, "strong");
    appendText(
      button,
      `${record.kind} · ${record.evidence_authority} · ${record.lifecycle_state}`,
      "span",
      "memory-row-meta",
    );
    appendText(
      button,
      `updated ${record.updated_at} · reinforced ${record.reinforcement_count} · retrieval ${record.eligible_for_normal_retrieval ? "eligible" : "ineligible"}`,
      "span",
      "memory-row-meta",
    );
    button.addEventListener("click", () => state.actions.selectMemory(record.fact_id));
    list.appendChild(button);
  }
  section.appendChild(list);
  if (state.list?.results_truncated) {
    appendText(section, "Results were truncated by the bounded backend query.", "p", "memory-help");
  }
  return section;
}

function renderEvidence(detail) {
  const container = document.createElement("div");
  const evidence = document.createElement("details");
  const evidenceSummary = document.createElement("summary");
  evidenceSummary.textContent = `Evidence (${detail.evidence_returned}/${detail.evidence_total})`;
  evidence.appendChild(evidenceSummary);
  for (const item of detail.evidence || []) {
    const row = document.createElement("p");
    row.textContent = `${item.authority} · session ${formatValue(item.source_session_id)} · turn ${formatValue(item.source_turn_id)} · field ${formatValue(item.source_field)} · ${item.observed_at}`;
    evidence.appendChild(row);
  }
  if (detail.evidence_truncated) appendText(evidence, "Additional evidence is not shown.", "p", "memory-help");

  const events = document.createElement("details");
  const eventsSummary = document.createElement("summary");
  eventsSummary.textContent = `Lifecycle (${detail.events_returned}/${detail.events_total})`;
  events.appendChild(eventsSummary);
  for (const item of detail.events || []) {
    const row = document.createElement("p");
    row.textContent = `${item.event_type}: ${formatValue(item.prior_state)} → ${formatValue(item.resulting_state)} · ${item.reason_code} · related ${formatValue(item.related_fact_id)} · ${item.occurred_at}`;
    events.appendChild(row);
  }
  if (detail.events_truncated) appendText(events, "Additional lifecycle events are not shown.", "p", "memory-help");
  container.append(evidence, events);
  return container;
}

function renderActions(state, record) {
  const section = document.createElement("section");
  section.className = "memory-actions";
  appendText(section, "Actions", "h4");
  const pending = state.mutationPending;
  const actionsEnabled = memoryActionsEnabled(record, pending);

  const confirm = document.createElement("button");
  confirm.type = "button";
  confirm.textContent = "Confirm";
  confirm.disabled = !actionsEnabled;
  confirm.addEventListener("click", () => state.actions.confirm());

  const dispute = document.createElement("button");
  dispute.type = "button";
  dispute.textContent = "Dispute";
  dispute.disabled = !actionsEnabled;
  dispute.addEventListener("click", () => state.actions.dispute());

  const forget = document.createElement("button");
  forget.type = "button";
  forget.textContent = "Forget";
  forget.disabled = !actionsEnabled;
  forget.addEventListener("click", () => state.actions.forget());

  const correction = document.createElement("form");
  correction.className = "memory-correction";
  const textLabel = document.createElement("label");
  textLabel.textContent = "Replacement text";
  const text = document.createElement("textarea");
  text.required = true;
  text.maxLength = 240;
  text.value = record.text || "";
  textLabel.appendChild(text);
  const valueLabel = document.createElement("label");
  valueLabel.textContent = "Replacement value (optional)";
  const value = document.createElement("input");
  value.type = "text";
  value.maxLength = 160;
  value.value = record.value || "";
  valueLabel.appendChild(value);
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.textContent = "Correct";
  submit.disabled = !actionsEnabled;
  correction.append(textLabel, valueLabel, submit);
  correction.addEventListener("submit", (event) => {
    event.preventDefault();
    const replacementText = text.value.trim();
    if (!replacementText) return;
    state.actions.correct({ replacementText, replacementValue: value.value.trim() || null });
  });

  const buttons = document.createElement("div");
  buttons.className = "memory-action-buttons";
  buttons.append(confirm, dispute, forget);
  section.append(buttons, correction);
  appendText(
    section,
    "Forgetting stops use of this semantic record. Source conversation and session artifacts are separate and are not erased by this operation.",
    "p",
    "memory-help",
  );
  return section;
}

function renderDetail(state) {
  const section = document.createElement("section");
  section.className = "memory-section memory-detail";
  appendText(section, "Detail", "h3");
  if (state.detailLoading) appendText(section, "Loading detail…", "p", "memory-help");
  if (state.detailError) appendText(section, state.detailError, "p", "memory-error");
  const detail = state.detail;
  if (!detail) {
    if (!state.detailLoading && !state.detailError) appendText(section, "Select a memory to inspect it.", "p", "memory-help");
    return section;
  }
  const record = detail.record;
  appendText(section, record.text, "p", "memory-claim");
  const facts = document.createElement("dl");
  facts.className = "memory-facts";
  labeledValue(facts, "Value", record.value);
  labeledValue(facts, "Kind", record.kind);
  labeledValue(facts, "Authority", record.evidence_authority);
  labeledValue(facts, "State", record.lifecycle_state);
  labeledValue(facts, "Retrieval", record.eligible_for_normal_retrieval ? "eligible" : "ineligible");
  labeledValue(facts, "Confidence", record.confidence);
  labeledValue(facts, "Importance", record.importance);
  labeledValue(facts, "Reinforcement", record.reinforcement_count);
  labeledValue(facts, "Revision", record.revision);
  labeledValue(facts, "Created", record.created_at);
  labeledValue(facts, "Updated", record.updated_at);
  labeledValue(facts, "Confirmed", record.confirmed_at);
  labeledValue(facts, "Expires", record.expires_at);
  labeledValue(facts, "Replacement", record.superseded_by_fact_id);
  section.append(facts, renderEvidence(detail), renderActions(state, record));
  if (detail.forgetting_scope) {
    appendText(section, detail.forgetting_scope, "p", "memory-help");
  }
  if (state.correction) {
    appendText(
      section,
      `${state.correction.relation}: ${state.correction.original.fact_id} → ${state.correction.replacement.fact_id}`,
      "p",
      "memory-notice",
    );
  }
  return section;
}

function renderPanel(container, state, actions) {
  const view = { ...state, actions };
  const header = document.createElement("div");
  header.className = "memory-panel-header";
  const heading = appendText(header, "Memory", "h2");
  heading.tabIndex = -1;
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Close";
  close.addEventListener("click", actions.close);
  header.appendChild(close);

  const messages = document.createElement("div");
  messages.setAttribute("aria-live", "polite");
  for (const message of [state.conflict, state.policyError, state.curationError, state.notice]) {
    if (message) appendText(messages, message, "p", message === state.notice ? "memory-notice" : "memory-error");
  }
  container.replaceChildren(
    header,
    messages,
    renderCuration(view),
    renderList(view),
    renderDetail(view),
  );
}

export function createMemoryPanel(container, handlers, options = {}) {
  let open = false;
  const confirmForget = options.confirmForget || ((message) => window.confirm(message));
  let controller;
  const actions = {
    close: () => close(),
    refreshList: (filters) => controller.refreshList(filters),
    selectMemory: (factId) => controller.selectMemory(factId),
    updatePolicy: (enabled) => controller.updatePolicy(enabled),
    confirm: () => controller.confirm(),
    correct: (payload) => controller.correct(payload),
    dispute: () => controller.dispute(),
    forget: () => controller.forget(confirmForget),
  };
  controller = createMemoryPanelController(handlers, (state) => {
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

export function createOperatorPanelCoordinator(options) {
  return {
    async toggleMemory() {
      if (options.isMemoryOpen()) {
        options.closeMemory();
        options.focusMemoryTrigger();
        return;
      }
      options.closeSettings();
      await options.openMemory();
    },
    async toggleSettings() {
      if (options.isSettingsOpen()) {
        options.closeSettings();
        options.focusSettingsTrigger();
        return;
      }
      options.closeMemory();
      await options.openSettings();
    },
  };
}
