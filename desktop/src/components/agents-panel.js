const AGENT_CAPABILITY_PREFIX = "agent-invoke-";

function errorMessage(error, fallback) {
  return error?.detail?.message || error?.message || fallback;
}

export function agentRunProfileId(record) {
  const capabilityId = String(record?.capability_id || "");
  return capabilityId.startsWith(AGENT_CAPABILITY_PREFIX)
    ? capabilityId.slice(AGENT_CAPABILITY_PREFIX.length)
    : "";
}

export function agentRunActivityState(record) {
  const status = record?.record?.status;
  if (status === "success" || status === "succeeded") return "succeeded";
  if (status === "cancelled") return "cancelled";
  if (status === "failure" || status === "failed") return "failed";
  if (status === "awaiting_approval") return "blocked";
  if (!status) return "idle";
  return "running";
}

export function agentInvokeNotice(payload) {
  const status = payload?.status;
  if (status === "awaiting_approval") return "Agent invocation is awaiting approval.";
  if (status === "success" || status === "succeeded") return "Agent run completed.";
  if (!status) return "Agent invocation returned no status.";
  return `Agent run reported ${status}.`;
}

export function agentCancelNotice(payload) {
  return payload?.cancelled ? "Agent run cancelled." : "No cancellable agent run was found.";
}

export function agentInvokeEnabled(agent, prompt, mutationPending) {
  return Boolean(agent?.invocation_modes?.includes("direct"))
    && agent?.enabled !== false
    && Boolean(prompt.trim())
    && !mutationPending;
}

const RESPONSE_ONLY_FIELDS = ["source", "editable", "enabled", "fingerprint"];

export const NEW_AGENT_PROFILE = {
  profile_id: "new-agent",
  display_name: "New agent",
  purpose: "Describe what this agent is for",
  instructions: "Describe how this agent should work.",
  invocation_modes: ["direct"],
  capability_ids: [],
  memory_scope: "none",
  approval_class: "standard",
  timeout_ms: 30000,
  cancellable: true,
  output_contract: { type: "object" },
  provider_model_policy: {},
  runtime: { kind: "internal" },
};

export function agentProfileDocument(agent) {
  const document = { ...agent };
  for (const key of RESPONSE_ONLY_FIELDS) delete document[key];
  return document;
}

export function parseAgentProfile(text) {
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new Error("The profile must be valid JSON.");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("The profile must be a JSON object.");
  }
  return parsed;
}

export function agentStateNotice(enabled) {
  return enabled ? "Agent enabled." : "Agent disabled.";
}

function copyState(state) {
  return {
    ...state,
    agents: [...state.agents],
    runs: [...state.runs],
  };
}

export function createAgentsPanelController(handlers, render = () => undefined) {
  const state = {
    agents: [],
    runs: [],
    selectedProfileId: "",
    prompt: "",
    agentsLoading: false,
    runsLoading: false,
    mutationPending: false,
    agentsError: "",
    runsError: "",
    mutationError: "",
    notice: "",
    editing: "",
    draft: "",
  };
  let agentsSequence = 0;
  let runsSequence = 0;

  function emit() {
    render(copyState(state));
  }

  async function refreshAgents() {
    if (!handlers.listAgents) return null;
    const request = ++agentsSequence;
    state.agentsLoading = true;
    state.agentsError = "";
    emit();
    try {
      const payload = await handlers.listAgents();
      if (request !== agentsSequence) return null;
      state.agents = payload?.agents || [];
      if (!state.agents.some((agent) => agent.profile_id === state.selectedProfileId)) {
        state.selectedProfileId = "";
      }
      return payload;
    } catch (error) {
      if (request !== agentsSequence) return null;
      state.agentsError = errorMessage(error, "Agents are unavailable.");
      return null;
    } finally {
      if (request === agentsSequence) {
        state.agentsLoading = false;
        emit();
      }
    }
  }

  async function refreshRuns() {
    if (!handlers.listAgentRuns) return null;
    const request = ++runsSequence;
    state.runsLoading = true;
    state.runsError = "";
    emit();
    try {
      const payload = await handlers.listAgentRuns();
      if (request !== runsSequence) return null;
      state.runs = payload?.records || [];
      return payload;
    } catch (error) {
      if (request !== runsSequence) return null;
      state.runsError = errorMessage(error, "Agent runs are unavailable.");
      return null;
    } finally {
      if (request === runsSequence) {
        state.runsLoading = false;
        emit();
      }
    }
  }

  function selectAgent(profileId) {
    state.selectedProfileId = profileId;
    state.notice = "";
    state.mutationError = "";
    emit();
  }

  function setPrompt(value) {
    state.prompt = value;
  }

  async function mutate(run, notice, { catalog = false } = {}) {
    if (state.mutationPending) return null;
    state.mutationPending = true;
    state.notice = "";
    state.mutationError = "";
    emit();
    try {
      const payload = await run();
      state.notice = notice(payload);
      await (catalog ? refreshAgents() : refreshRuns());
      return payload;
    } catch (error) {
      state.mutationError = errorMessage(error, "That agent request could not be completed.");
      return null;
    } finally {
      state.mutationPending = false;
      emit();
    }
  }

  async function invoke(profileId, prompt) {
    const payload = await mutate(() => handlers.invokeAgent(profileId, prompt), agentInvokeNotice);
    if (payload) state.prompt = "";
    return payload;
  }

  async function cancel(profileId) {
    return mutate(() => handlers.cancelAgent(profileId), agentCancelNotice);
  }

  function agentById(profileId) {
    return state.agents.find((agent) => agent.profile_id === profileId) || null;
  }

  function startCreate() {
    state.editing = "new";
    state.draft = JSON.stringify(NEW_AGENT_PROFILE, null, 2);
    state.notice = "";
    state.mutationError = "";
    emit();
  }

  function startEdit(profileId) {
    const agent = agentById(profileId);
    if (!agent?.editable) return;
    state.editing = profileId;
    state.draft = JSON.stringify(agentProfileDocument(agent), null, 2);
    state.notice = "";
    state.mutationError = "";
    emit();
  }

  function setDraft(value) {
    state.draft = value;
  }

  function cancelEdit() {
    state.editing = "";
    state.draft = "";
    emit();
  }

  async function save() {
    let profile;
    try {
      profile = parseAgentProfile(state.draft);
    } catch (error) {
      state.mutationError = error.message;
      emit();
      return null;
    }
    const editing = state.editing;
    const payload = await mutate(
      () => (editing === "new"
        ? handlers.createAgent(profile)
        : handlers.updateAgent(editing, profile, agentById(editing)?.fingerprint)),
      () => "Agent profile saved.",
      { catalog: true },
    );
    if (payload) {
      state.editing = "";
      state.draft = "";
      state.selectedProfileId = payload.profile_id || state.selectedProfileId;
      emit();
    }
    return payload;
  }

  async function remove(profileId) {
    const agent = agentById(profileId);
    if (!agent?.editable) return null;
    return mutate(
      () => handlers.deleteAgent(profileId, agent.fingerprint),
      () => "Agent profile deleted.",
      { catalog: true },
    );
  }

  async function setEnabled(profileId, enabled) {
    return mutate(
      () => handlers.setExtensionState(`agent:${profileId}`, enabled ? "enabled" : "disabled"),
      () => agentStateNotice(enabled),
      { catalog: true },
    );
  }

  async function load() {
    await Promise.all([refreshAgents(), refreshRuns()]);
  }

  function cancelPendingReads() {
    agentsSequence += 1;
    runsSequence += 1;
    state.agentsLoading = false;
    state.runsLoading = false;
  }

  emit();
  return {
    load,
    refreshAgents,
    refreshRuns,
    selectAgent,
    setPrompt,
    invoke,
    cancel,
    startCreate,
    startEdit,
    setDraft,
    cancelEdit,
    save,
    remove,
    setEnabled,
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
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function labeledValue(parent, label, value) {
  const field = document.createElement("div");
  field.className = "agents-field";
  appendText(field, label, "dt");
  appendText(field, formatValue(value), "dd");
  parent.appendChild(field);
  return field;
}

function selectedAgent(state) {
  return state.agents.find((agent) => agent.profile_id === state.selectedProfileId) || null;
}

function renderCatalog(state) {
  const section = document.createElement("section");
  section.className = "agents-section";
  appendText(section, "Agents", "h3");
  const create = document.createElement("button");
  create.type = "button";
  create.textContent = "New agent";
  create.disabled = state.mutationPending || Boolean(state.editing);
  create.addEventListener("click", () => state.actions.startCreate());
  section.appendChild(create);
  if (state.agentsLoading) {
    appendText(section, "Loading agents…", "p", "agents-help");
    return section;
  }
  if (state.agentsError) {
    appendText(section, state.agentsError, "p", "agents-error");
    return section;
  }
  if (!state.agents.length) {
    appendText(section, "No agent profiles are registered.", "p", "agents-help");
    return section;
  }
  const list = document.createElement("ul");
  list.className = "agents-list";
  for (const agent of state.agents) {
    const item = document.createElement("li");
    const row = document.createElement("button");
    row.type = "button";
    row.className = "agents-row";
    row.setAttribute("aria-pressed", agent.profile_id === state.selectedProfileId ? "true" : "false");
    appendText(row, agent.display_name || agent.profile_id, "strong");
    appendText(row, agent.purpose, "span", "agents-row-meta");
    appendText(row, formatValue(agent.invocation_modes), "span", "agents-row-meta");
    if (agent.enabled === false) appendText(row, "disabled", "span", "agents-row-meta");
    row.addEventListener("click", () => state.actions.selectAgent(agent.profile_id));
    item.appendChild(row);
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

function renderDetail(state) {
  const section = document.createElement("section");
  section.className = "agents-section";
  appendText(section, "Agent detail", "h3");
  const agent = selectedAgent(state);
  if (!agent) {
    appendText(section, "Select an agent to see its contract.", "p", "agents-help");
    return section;
  }
  appendText(section, agent.display_name || agent.profile_id, "strong");
  appendText(section, agent.purpose, "p", "agents-help");
  const facts = document.createElement("dl");
  facts.className = "agents-facts";
  labeledValue(facts, "Profile", agent.profile_id);
  labeledValue(facts, "Invocation", agent.invocation_modes);
  labeledValue(facts, "Approval", agent.approval_class);
  labeledValue(facts, "Capabilities", agent.capability_ids);
  labeledValue(facts, "Memory scope", agent.memory_scope);
  labeledValue(facts, "Cancellable", agent.cancellable);
  labeledValue(facts, "Runs in", agentRuntimeLabel(agent.runtime));
  labeledValue(facts, "Owner", agent.editable ? "Operator" : "Application (read-only)");
  labeledValue(facts, "Enabled", agent.enabled !== false);
  section.appendChild(facts);

  if (agent.enabled === false) {
    appendText(section, "This agent is disabled. Enable it to invoke it.", "p", "agents-help");
  } else if (!agent.invocation_modes?.includes("direct")) {
    appendText(section, "This agent is not invocable directly from the operator surface.", "p", "agents-help");
  } else {
    const form = document.createElement("form");
    form.className = "agents-invoke";
    const label = document.createElement("label");
    appendText(label, "Prompt");
    const prompt = document.createElement("textarea");
    prompt.name = "prompt";
    prompt.required = true;
    prompt.value = state.prompt;
    // The prompt draft lives in controller state so a run refresh does not discard it, and it is
    // not re-emitted on input so typing never re-renders the textarea out from under the caret.
    prompt.addEventListener("input", (event) => state.actions.setPrompt(event.target.value));
    label.appendChild(prompt);
    form.appendChild(label);
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.textContent = "Invoke agent";
    submit.disabled = state.mutationPending;
    form.appendChild(submit);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!agentInvokeEnabled(agent, prompt.value, state.mutationPending)) return;
      state.actions.setPrompt(prompt.value);
      state.actions.invoke(agent.profile_id, prompt.value);
    });
    section.appendChild(form);
  }

  const buttons = document.createElement("div");
  buttons.className = "agents-buttons";
  const cancelButton = document.createElement("button");
  cancelButton.type = "button";
  cancelButton.textContent = "Cancel run";
  cancelButton.disabled = !agent.cancellable || state.mutationPending;
  if (!agent.cancellable) cancelButton.title = "This agent profile is not cancellable.";
  cancelButton.addEventListener("click", () => state.actions.cancel(agent.profile_id));
  buttons.appendChild(cancelButton);
  const enabled = agent.enabled !== false;
  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.textContent = enabled ? "Disable" : "Enable";
  toggle.disabled = state.mutationPending;
  toggle.addEventListener("click", () => state.actions.setEnabled(agent.profile_id, !enabled));
  buttons.appendChild(toggle);
  if (agent.editable) {
    const edit = document.createElement("button");
    edit.type = "button";
    edit.textContent = "Edit profile";
    edit.disabled = state.mutationPending || Boolean(state.editing);
    edit.addEventListener("click", () => state.actions.startEdit(agent.profile_id));
    buttons.appendChild(edit);
    const remove = document.createElement("button");
    remove.type = "button";
    remove.textContent = "Delete profile";
    remove.disabled = state.mutationPending;
    remove.addEventListener("click", () => state.actions.remove(agent.profile_id));
    buttons.appendChild(remove);
  }
  section.appendChild(buttons);
  return section;
}

function agentRuntimeLabel(runtime) {
  if (runtime?.kind === "acp") return `External agent (${runtime.adapter_id})`;
  return "JARVIS";
}

function renderEditor(state) {
  const section = document.createElement("section");
  section.className = "agents-section";
  appendText(section, state.editing === "new" ? "New agent profile" : "Edit agent profile", "h3");
  const form = document.createElement("form");
  form.className = "agents-invoke";
  const label = document.createElement("label");
  appendText(label, "Profile (JSON)");
  const draft = document.createElement("textarea");
  draft.name = "profile";
  draft.rows = 16;
  draft.value = state.draft;
  draft.addEventListener("input", (event) => state.actions.setDraft(event.target.value));
  label.appendChild(draft);
  form.appendChild(label);
  const buttons = document.createElement("div");
  buttons.className = "agents-buttons";
  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "Save profile";
  save.disabled = state.mutationPending;
  buttons.appendChild(save);
  const discard = document.createElement("button");
  discard.type = "button";
  discard.textContent = "Discard changes";
  discard.addEventListener("click", () => state.actions.cancelEdit());
  buttons.appendChild(discard);
  form.appendChild(buttons);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    state.actions.setDraft(draft.value);
    state.actions.save();
  });
  section.appendChild(form);
  return section;
}

function renderRuns(state) {
  const section = document.createElement("section");
  section.className = "agents-section";
  appendText(section, "Runs", "h3");
  if (state.runsLoading) {
    appendText(section, "Loading agent runs…", "p", "agents-help");
    return section;
  }
  if (state.runsError) {
    appendText(section, state.runsError, "p", "agents-error");
    return section;
  }
  if (!state.runs.length) {
    appendText(section, "No agent evidence has been recorded.", "p", "agents-help");
    return section;
  }
  const list = document.createElement("ul");
  list.className = "agents-list";
  for (const record of state.runs) {
    const item = document.createElement("li");
    appendText(item, `${record.kind} · ${agentRunProfileId(record) || record.capability_id}`, "strong");
    const status = appendText(item, formatValue(record.record?.status), "span", "agents-status");
    status.dataset.state = agentRunActivityState(record);
    appendText(item, formatValue(record.recorded_at), "span", "agents-row-meta");
    if (record.record?.error) appendText(item, record.record.error, "p", "agents-error");
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

function renderPanel(container, state, actions) {
  const view = { ...state, actions };
  const header = document.createElement("div");
  header.className = "agents-panel-header";
  const heading = appendText(header, "Agents", "h2");
  heading.tabIndex = -1;

  const messages = document.createElement("div");
  messages.setAttribute("aria-live", "polite");
  if (state.notice) appendText(messages, state.notice, "p", "agents-notice");
  if (state.mutationError) appendText(messages, state.mutationError, "p", "agents-error");

  const sections = [renderCatalog(view)];
  sections.push(state.editing ? renderEditor(view) : renderDetail(view));
  container.replaceChildren(header, messages, ...sections, renderRuns(view));
}

export function createAgentsPanel(container, handlers, options = {}) {
  let open = false;
  let controller;
  const actions = {
    close: () => close(),
    selectAgent: (profileId) => controller.selectAgent(profileId),
    setPrompt: (value) => controller.setPrompt(value),
    invoke: (profileId, prompt) => controller.invoke(profileId, prompt),
    cancel: (profileId) => controller.cancel(profileId),
    startCreate: () => controller.startCreate(),
    startEdit: (profileId) => controller.startEdit(profileId),
    setDraft: (value) => controller.setDraft(value),
    cancelEdit: () => controller.cancelEdit(),
    save: () => controller.save(),
    remove: (profileId) => controller.remove(profileId),
    setEnabled: (profileId, enabled) => controller.setEnabled(profileId, enabled),
  };
  controller = createAgentsPanelController(handlers, (state) => {
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
