import { confirmDestructive } from "./ui/confirm.js";
import { appendText, button, buttonRow, details, facts, field, option, statusBadge } from "./ui/dom.js";
import { errorMessage, formatTime, humanize, isConflict, statusText } from "./ui/format.js";
import { createPanelLifecycle, messageRegion, renderPanelHeader, section, sectionState } from "./ui/panel.js";
import { TEXT } from "./ui/vocabulary.js";

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


export function formatCurationResult(result) {
  if (!result) return "";
  return [
    humanize(result.reason_code),
    `proposed ${result.candidates_proposed}`,
    `pending review ${result.pending_review_created}`,
    `active ${result.active_records_created}`,
    `rejected ${result.candidates_rejected}`,
    `duplicates ${result.duplicate_noops}`,
    `reinforced ${result.records_reinforced}`,
    `superseded/disputed ${result.records_superseded_or_disputed}`,
    `failures ${result.failure_count}`,
  ].join(" · ");
}

function copyState(state) {
  return {
    ...state,
    filters: { ...state.filters },
    layers: state.layers ? { ...state.layers, layers: [...(state.layers.layers || [])] } : null,
    retentionPolicy: state.retentionPolicy ? { ...state.retentionPolicy } : null,
    list: state.list ? { ...state.list, records: [...(state.list.records || [])] } : null,
  };
}

export function createMemoryPanelController(handlers, render = () => undefined) {
  const state = {
    filters: { lifecycleState: null, kind: null, query: null, offset: 0, limit: 20 },
    policy: null,
    layers: null,
    retentionPolicy: null,
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
    contractError: "",
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

  async function refreshContracts() {
    if (!handlers.getMemoryLayers || !handlers.getArtifactRetentionPolicy) return null;
    try {
      const [layers, retentionPolicy] = await Promise.all([
        handlers.getMemoryLayers(),
        handlers.getArtifactRetentionPolicy(),
      ]);
      state.layers = layers;
      state.retentionPolicy = retentionPolicy;
      state.contractError = "";
    } catch (error) {
      state.contractError = errorMessage(error, "Memory contracts are unavailable.");
    }
    emit();
    return { layers: state.layers, retentionPolicy: state.retentionPolicy };
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
    await Promise.all([refreshPolicy(), refreshContracts(), refreshCuration(), refreshList()]);
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
    refreshContracts,
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

export function memoryActionsEnabled(record, mutationPending) {
  return Boolean(record) && !mutationPending;
}

export function curationActivityState(status) {
  if (!status.service_available || !status.processor_available || status.retry_blocked) return "blocked";
  if (status.degraded) return "degraded";
  if (status.drain_active || status.current_job_id || Number(status.processing_count) > 0) return "running";
  return "idle";
}

const CURATION_TEXT = { blocked: "Unavailable", degraded: "Degraded", running: "Processing", idle: "Idle" };
const LIFECYCLE_TEXT = { pending_review: "Waiting for review" };

function renderCuration(state) {
  const node = section("Policy & curation");

  if (state.policy) {
    const label = document.createElement("label");
    label.className = "panel-choice";
    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.checked = Boolean(state.policy.automatic_curation_enabled);
    toggle.disabled = state.policyPending;
    toggle.dataset.focusKey = "memory:policy";
    toggle.addEventListener("change", () => state.actions.updatePolicy(toggle.checked));
    label.append(toggle, document.createTextNode("Automatic retention (opt-in)"));
    node.appendChild(label);
    appendText(
      node,
      "Model-proposed memories remain application-governed. Enabling this allows automatic review; it does not bypass lifecycle controls.",
      "p",
      "panel-help",
    );
  } else if (!state.policyError) {
    appendText(node, TEXT.loading("memory policy"), "p", "panel-help");
  }

  const status = state.curation;
  if (status) {
    const statusName = curationActivityState(status);
    node.appendChild(statusBadge(CURATION_TEXT[statusName], statusName));
    node.appendChild(facts([
      ["Pending", status.pending_count],
      ["Processing", status.processing_count],
      ["Failed", status.failed_count],
      ["Reason", humanize(status.degraded_reason || status.last_result_reason)],
      ["Processor result", formatCurationResult(status.last_result)],
      ["Updated", formatTime(status.last_updated_at)],
    ]));
    const jobs = details([["Current job", status.current_job_id]], null, `Recent jobs (${status.jobs_returned || 0})`);
    for (const job of status.recent_jobs || []) {
      const result = formatCurationResult(job.result);
      appendText(jobs, `${statusText(job.status)} · ${result || humanize(job.last_reason || job.blocked_reason || "no reason")} · queued ${formatTime(job.enqueued_at)} · finished ${formatTime(job.completed_at)}`, "p", "panel-help");
    }
    node.appendChild(jobs);
  } else if (!state.curationError) {
    appendText(node, TEXT.loading("curation status"), "p", "panel-help");
  }
  return node;
}

function renderContracts(state) {
  const node = section("Layers & retention");
  if (sectionState(node, { error: state.contractError })) return node;
  const layerRows = state.layers?.layers || [];
  if (!layerRows.length && !state.retentionPolicy) {
    appendText(node, TEXT.loading("memory contracts"), "p", "panel-help");
    return node;
  }
  const count = (value) => layerRows.filter((item) => item.implementation_state === value).length;
  node.appendChild(facts([
    ["Implemented layers", count("implemented")],
    ["Defined next", count("defined_next")],
    ["Decisions required", count("decision_required")],
    ["Artifact owner", humanize(state.retentionPolicy?.source_artifact_owner)],
    ["Physical erasure", state.retentionPolicy?.physical_erasure_available],
  ]));
  if (state.retentionPolicy?.source_artifact_erasure_scope) {
    appendText(node, state.retentionPolicy.source_artifact_erasure_scope, "p", "panel-help");
  }
  return node;
}

function renderFilters(state) {
  const form = document.createElement("form");
  form.className = "memory-filters";
  const search = document.createElement("input");
  search.type = "search";
  search.maxLength = 240;
  search.value = state.filters.query || "";
  search.dataset.draftKey = "memory:search";

  const kind = document.createElement("select");
  kind.dataset.draftKey = "memory:kind";
  kind.appendChild(option("", "Default kinds"));
  for (const value of MEMORY_KINDS) kind.appendChild(option(value, humanize(value)));
  kind.value = state.filters.kind || "";

  const lifecycle = document.createElement("select");
  lifecycle.dataset.draftKey = "memory:lifecycle";
  lifecycle.appendChild(option("", "Active + review"));
  for (const value of MEMORY_STATES) lifecycle.appendChild(option(value, humanize(value, LIFECYCLE_TEXT)));
  lifecycle.value = state.filters.lifecycleState || "";

  form.append(
    field("Search", search),
    field("Kind", kind),
    field("Lifecycle", lifecycle),
    buttonRow(button("Apply", { type: "submit", disabled: state.listLoading, focusKey: "memory:apply" })),
  );
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
  const node = section("Records");
  node.appendChild(renderFilters(state));
  if (state.listLoading) appendText(node, TEXT.loading("records"), "p", "panel-help");
  if (state.listError) appendText(node, state.listError, "p", "panel-error");
  const records = state.list?.records || [];
  if (!state.listLoading && !state.listError && records.length === 0) {
    appendText(node, "No memories match these filters.", "p", "panel-help");
  }
  const list = document.createElement("div");
  list.className = "memory-list";
  list.dataset.scrollKey = "memory:list";
  for (const record of records) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "memory-row";
    row.dataset.state = record.lifecycle_state;
    row.dataset.focusKey = `memory:${record.fact_id}`;
    row.setAttribute("aria-pressed", state.detail?.record?.fact_id === record.fact_id ? "true" : "false");
    appendText(row, record.text, "strong");
    appendText(row, `${humanize(record.kind)} · ${humanize(record.evidence_authority)} · ${humanize(record.lifecycle_state, LIFECYCLE_TEXT)}`, "span", "panel-help");
    appendText(
      row,
      `Updated ${formatTime(record.updated_at)} · reinforced ${record.reinforcement_count} · ${record.eligible_for_normal_retrieval ? "used in answers" : "not used in answers"}`,
      "span",
      "panel-help",
    );
    row.addEventListener("click", () => state.actions.selectMemory(record.fact_id));
    list.appendChild(row);
  }
  node.appendChild(list);
  if (state.list?.results_truncated) {
    appendText(node, "More memories match; narrow the filters to see them.", "p", "panel-help");
  }
  return node;
}

function renderEvidence(detail) {
  const container = document.createElement("div");
  const evidence = details([], null, `Evidence (${detail.evidence_returned}/${detail.evidence_total})`);
  for (const item of detail.evidence || []) {
    appendText(evidence, `${humanize(item.authority)} · ${formatTime(item.observed_at)}`, "p", "panel-help");
    evidence.appendChild(facts([["Session", item.source_session_id], ["Turn", item.source_turn_id], ["Field", item.source_field]]));
  }
  if (detail.evidence_truncated) appendText(evidence, "Additional evidence is not shown.", "p", "panel-help");

  const events = details([], null, `Lifecycle (${detail.events_returned}/${detail.events_total})`);
  for (const item of detail.events || []) {
    appendText(events, `${humanize(item.event_type)}: ${humanize(item.prior_state, LIFECYCLE_TEXT)} → ${humanize(item.resulting_state, LIFECYCLE_TEXT)} · ${humanize(item.reason_code)} · ${formatTime(item.occurred_at)}`, "p", "panel-help");
  }
  if (detail.events_truncated) appendText(events, "Additional lifecycle events are not shown.", "p", "panel-help");
  container.append(evidence, events);
  return container;
}

function renderReview(state, record) {
  const node = document.createElement("section");
  node.className = "memory-actions";
  appendText(node, "Review", "h4");
  const enabled = memoryActionsEnabled(record, state.mutationPending);

  const text = document.createElement("textarea");
  text.required = true;
  text.maxLength = 240;
  text.value = record.text || "";
  text.dataset.draftKey = `memory:${record.fact_id}:replacement-text`;
  const value = document.createElement("input");
  value.type = "text";
  value.maxLength = 160;
  value.value = record.value || "";
  value.dataset.draftKey = `memory:${record.fact_id}:replacement-value`;
  const correction = document.createElement("form");
  correction.className = "memory-correction";
  correction.append(
    field("Replacement text", text),
    field("Replacement value (optional)", value),
    buttonRow(button("Correct", { type: "submit", disabled: !enabled, focusKey: "memory:correct" })),
  );
  correction.addEventListener("submit", (event) => {
    event.preventDefault();
    const replacementText = text.value.trim();
    if (!replacementText) return;
    state.actions.correct({ replacementText, replacementValue: value.value.trim() || null });
  });

  node.append(
    buttonRow(
      button("Confirm", { variant: "primary", disabled: !enabled, onClick: () => state.actions.confirm(), focusKey: "memory:confirm" }),
      button("Dispute", { disabled: !enabled, onClick: () => state.actions.dispute(), focusKey: "memory:dispute" }),
      button("Forget", { variant: "danger", disabled: !enabled, onClick: () => state.actions.forget(), focusKey: "memory:forget" }),
    ),
    correction,
  );
  appendText(
    node,
    "Forgetting stops use of this memory. The conversations it came from are separate and are not erased by this operation.",
    "p",
    "panel-help",
  );
  return node;
}

function renderDetail(state) {
  const node = section("Memory detail");
  if (state.detailLoading) appendText(node, TEXT.loading("the memory"), "p", "panel-help");
  if (state.detailError) appendText(node, state.detailError, "p", "panel-error");
  const detail = state.detail;
  if (!detail) {
    if (!state.detailLoading && !state.detailError) appendText(node, "Select a memory to review it.", "p", "panel-help");
    return node;
  }
  const record = detail.record;
  appendText(node, record.text, "p", "memory-claim");
  node.appendChild(facts([
    ["Value", record.value],
    ["Kind", humanize(record.kind)],
    ["Authority", humanize(record.evidence_authority)],
    ["State", humanize(record.lifecycle_state, LIFECYCLE_TEXT)],
    ["Used in answers", record.eligible_for_normal_retrieval],
    ["Confidence", record.confidence],
    ["Importance", record.importance],
    ["Reinforcement", record.reinforcement_count],
    ["Created", formatTime(record.created_at)],
    ["Updated", formatTime(record.updated_at)],
    ["Confirmed", formatTime(record.confirmed_at)],
    ["Expires", formatTime(record.expires_at)],
  ]));
  node.appendChild(details([["Memory", record.fact_id], ["Revision", record.revision], ["Replaced by", record.superseded_by_fact_id]]));
  node.append(renderEvidence(detail), renderReview(state, record));
  if (detail.forgetting_scope) appendText(node, detail.forgetting_scope, "p", "panel-help");
  if (state.correction) {
    appendText(node, `${humanize(state.correction.relation)}: the corrected memory replaces the original.`, "p", "panel-notice");
    node.appendChild(details([
      ["Original", state.correction.original.fact_id],
      ["Replacement", state.correction.replacement.fact_id],
    ]));
  }
  return node;
}

function renderPanel(state) {
  const errors = [state.conflict, state.policyError, state.contractError, state.curationError].filter(Boolean).join(" ");
  const layout = document.createElement("div");
  layout.className = "memory-panel-layout";
  layout.append(renderList(state), renderDetail(state));

  return [
    renderPanelHeader("Memory"),
    messageRegion({ notice: state.notice, error: errors }),
    renderContracts(state),
    renderCuration(state),
    layout,
  ];
}

export function createMemoryPanel(container, handlers, options = {}) {
  const confirmForget = options.confirmForget || confirmDestructive;
  let controller;
  const actions = {
    refreshList: (filters) => controller.refreshList(filters),
    selectMemory: (factId) => controller.selectMemory(factId),
    updatePolicy: (enabled) => controller.updatePolicy(enabled),
    confirm: () => controller.confirm(),
    correct: (payload) => controller.correct(payload),
    dispute: () => controller.dispute(),
    forget: () => controller.forget(confirmForget),
  };
  const lifecycle = createPanelLifecycle(container, {
    load: () => controller.load(),
    render: (state) => renderPanel({ ...state, actions }),
    cancelPendingReads: () => controller.cancelPendingReads(),
    onClose: options.onClose,
  });
  controller = createMemoryPanelController(handlers, lifecycle.draw);
  return { open: lifecycle.open, close: lifecycle.close, isOpen: lifecycle.isOpen, controller };
}
