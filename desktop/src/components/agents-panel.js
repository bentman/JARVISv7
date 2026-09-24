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

export const INVOCATION_MODE_LABELS = {
  direct: "Run it from this panel",
  as_tool: "Let JARVIS use it when helpful",
  router_selected: "Answer when I address it by name",
  handoff: "Let it take over the conversation",
};

export const APPROVAL_LABELS = {
  none: "Runs without asking",
  standard: "Ask me before it runs",
  strict: "Always ask me before it runs",
};

export const MEMORY_SCOPE_LABELS = {
  none: "No memory",
  working: "This conversation",
  episodic: "This conversation and past conversations",
  semantic: "This conversation and known facts",
  full: "All memory",
};

const PROFILE_DEFAULTS = {
  output_contract: { type: "object" },
  provider_model_policy: {},
};

export function agentProfileDocument(agent) {
  const document = { ...agent };
  for (const key of RESPONSE_ONLY_FIELDS) delete document[key];
  return document;
}

export function agentModesSummary(modes) {
  return (modes || []).map((mode) => INVOCATION_MODE_LABELS[mode] || mode).join(" · ") || "Not reachable";
}

export function profileIdFromName(name) {
  return String(name || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function formFromDocument(document, overrides = {}) {
  return {
    profile_id: document.profile_id || "",
    display_name: document.display_name || "",
    purpose: document.purpose || "",
    instructions: document.instructions || "",
    modes: [...(document.invocation_modes || [])],
    approval_class: document.approval_class || "standard",
    memory_scope: document.memory_scope || "none",
    capability_ids: [...(document.capability_ids || [])],
    timeout_seconds: Math.round((document.timeout_ms || 30000) / 1000),
    cancellable: document.cancellable !== false,
    runtime_kind: document.runtime?.kind || "internal",
    adapter_id: document.runtime?.adapter_id || "",
    base: document,
    ...overrides,
  };
}

export function newAgentForm() {
  return formFromDocument({ invocation_modes: ["direct"] });
}

export function agentFormFromProfile(agent) {
  return formFromDocument(agentProfileDocument(agent));
}

export function duplicateAgentForm(agent) {
  const document = agentProfileDocument(agent);
  return formFromDocument(document, {
    profile_id: profileIdFromName(`${document.profile_id}-copy`),
    display_name: `${document.display_name} (copy)`,
  });
}

export function agentFormErrors(form) {
  if (!form.display_name.trim()) return "Give the agent a name.";
  if (!(form.profile_id.trim() || profileIdFromName(form.display_name))) {
    return "The name needs at least one letter or number.";
  }
  if (!form.purpose.trim()) return "Say what the agent is for.";
  if (!form.instructions.trim()) return "Tell the agent how to work.";
  if (!form.modes.length) return "Choose at least one way to reach the agent.";
  const seconds = Number(form.timeout_seconds);
  if (!Number.isInteger(seconds) || seconds < 1 || seconds > 600) {
    return "The time limit must be a whole number of seconds from 1 to 600.";
  }
  if (form.runtime_kind === "acp" && !form.adapter_id.trim()) {
    return "Name the external agent definition it runs in.";
  }
  return "";
}

export function agentProfileFromForm(form) {
  return {
    ...PROFILE_DEFAULTS,
    ...form.base,
    profile_id: form.profile_id.trim() || profileIdFromName(form.display_name),
    display_name: form.display_name.trim(),
    purpose: form.purpose.trim(),
    instructions: form.instructions.trim(),
    invocation_modes: Object.keys(INVOCATION_MODE_LABELS).filter((mode) => form.modes.includes(mode)),
    approval_class: form.approval_class,
    memory_scope: form.memory_scope,
    capability_ids: [...form.capability_ids],
    timeout_ms: Number(form.timeout_seconds) * 1000,
    cancellable: form.runtime_kind === "acp" ? true : Boolean(form.cancellable),
    runtime: form.runtime_kind === "acp"
      ? { kind: "acp", adapter_id: form.adapter_id.trim() }
      : { kind: "internal" },
  };
}

export function agentToolLabel(tool) {
  const notes = [tool.needs_approval ? "asks you first" : "", tool.available ? "" : "unavailable now"].filter(Boolean);
  return notes.length ? `${tool.label} (${notes.join(", ")})` : tool.label;
}

export function agentStateNotice(enabled) {
  return enabled ? "Agent enabled." : "Agent disabled.";
}

export function handoffStatusText(activeAgent) {
  return activeAgent ? `Talking to ${activeAgent.display_name || activeAgent.profile_id}` : "";
}

export function createHandoffStatus({ label, endButton, endHandoff, onEnded, onError }) {
  let sessionId = "";
  endButton.addEventListener("click", async () => {
    if (!sessionId) return;
    endButton.disabled = true;
    try {
      await endHandoff(sessionId);
      await onEnded?.();
    } catch (error) {
      endButton.disabled = false;
      onError(error);
    }
  });
  return {
    render(status) {
      const activeAgent = status?.active_agent || null;
      sessionId = activeAgent ? status.session_id || "" : "";
      label.textContent = handoffStatusText(activeAgent);
      endButton.hidden = !activeAgent;
      endButton.disabled = false;
    },
  };
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
    form: null,
    tools: [],
    toolsError: "",
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

  async function refreshTools() {
    if (!handlers.listAgentTools) return;
    try {
      const payload = await handlers.listAgentTools();
      state.tools = payload?.tools || [];
      state.toolsError = "";
    } catch (error) {
      state.toolsError = errorMessage(error, "The list of tools is unavailable.");
    }
    if (state.form) emit();
  }

  function openForm(editing, form) {
    state.editing = editing;
    state.form = form;
    state.notice = "";
    state.mutationError = "";
    emit();
    return refreshTools();
  }

  function startCreate() {
    return openForm("new", newAgentForm());
  }

  function startDuplicate(profileId) {
    const agent = agentById(profileId);
    return agent ? openForm("new", duplicateAgentForm(agent)) : null;
  }

  function startEdit(profileId) {
    const agent = agentById(profileId);
    return agent?.editable ? openForm(profileId, agentFormFromProfile(agent)) : null;
  }

  // Text fields update the form without re-rendering, so typing never loses the caret; only
  // choices that change which fields are shown re-render.
  function setField(name, value, { rerender = false } = {}) {
    if (!state.form) return;
    state.form = { ...state.form, [name]: value };
    if (rerender) emit();
  }

  function setMode(mode, checked) {
    if (!state.form) return;
    const modes = state.form.modes.filter((item) => item !== mode);
    state.form = { ...state.form, modes: checked ? [...modes, mode] : modes };
  }

  function setTool(capabilityId, checked) {
    if (!state.form) return;
    const tools = state.form.capability_ids.filter((item) => item !== capabilityId);
    state.form = { ...state.form, capability_ids: checked ? [...tools, capabilityId] : tools };
  }

  function cancelEdit() {
    state.editing = "";
    state.form = null;
    emit();
  }

  async function save() {
    if (!state.form) return null;
    const problem = agentFormErrors(state.form);
    if (problem) {
      state.mutationError = problem;
      emit();
      return null;
    }
    const profile = agentProfileFromForm(state.form);
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
      state.form = null;
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
    startDuplicate,
    startEdit,
    setField,
    setMode,
    setTool,
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
    appendText(row, agentModesSummary(agent.invocation_modes), "span", "agents-row-meta");
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
  labeledValue(facts, "Reached by", agentModesSummary(agent.invocation_modes));
  labeledValue(facts, "Approval", APPROVAL_LABELS[agent.approval_class] || agent.approval_class);
  labeledValue(facts, "Memory it can read", MEMORY_SCOPE_LABELS[agent.memory_scope] || agent.memory_scope);
  labeledValue(facts, "Tools it may use", agent.capability_ids?.length ? `${agent.capability_ids.length} allowed` : "None");
  labeledValue(facts, "Can be stopped", agent.cancellable);
  labeledValue(facts, "Runs in", agentRuntimeLabel(agent.runtime));
  labeledValue(facts, "Owner", agent.editable ? "You (editable)" : "Built in (duplicate it to change it)");
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
  } else {
    const duplicate = document.createElement("button");
    duplicate.type = "button";
    duplicate.textContent = "Duplicate as my agent";
    duplicate.disabled = state.mutationPending || Boolean(state.editing);
    duplicate.addEventListener("click", () => state.actions.startDuplicate(agent.profile_id));
    buttons.appendChild(duplicate);
  }
  section.appendChild(buttons);
  return section;
}

function agentRuntimeLabel(runtime) {
  if (runtime?.kind === "acp") return `External agent (${runtime.adapter_id})`;
  return "JARVIS";
}

function formField(parent, labelText, control, help = "") {
  const label = document.createElement("label");
  label.className = "agents-field-control";
  appendText(label, labelText);
  label.appendChild(control);
  if (help) appendText(label, help, "span", "agents-help");
  parent.appendChild(label);
  return control;
}

function textControl(state, name, { multiline = false, rows = 3 } = {}) {
  const control = document.createElement(multiline ? "textarea" : "input");
  if (multiline) control.rows = rows;
  else control.type = "text";
  control.name = name;
  control.value = state.form[name];
  control.addEventListener("input", (event) => state.actions.setField(name, event.target.value));
  return control;
}

function selectControl(state, name, labels, { rerender = false } = {}) {
  const control = document.createElement("select");
  control.name = name;
  for (const [value, text] of Object.entries(labels)) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    option.selected = state.form[name] === value;
    control.appendChild(option);
  }
  control.addEventListener("change", (event) => state.actions.setField(name, event.target.value, { rerender }));
  return control;
}

function renderToolChoices(state) {
  const tools = document.createElement("fieldset");
  tools.className = "agents-choices";
  appendText(tools, "Tools it may use", "legend");
  const known = new Set(state.tools.map((tool) => tool.capability_id));
  // A tool already allowed but no longer offered stays listed, so saving never drops it silently.
  const choices = [
    ...state.tools,
    ...state.form.capability_ids
      .filter((id) => !known.has(id))
      .map((id) => ({ capability_id: id, label: id, needs_approval: false, available: false })),
  ];
  if (state.toolsError) appendText(tools, state.toolsError, "p", "agents-error");
  if (!choices.length) {
    appendText(tools, "No tools are available. Add them in Extensions.", "p", "agents-help");
    return tools;
  }
  for (const tool of choices) {
    const option = document.createElement("label");
    option.className = "agents-choice";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.name = `tool-${tool.capability_id}`;
    box.checked = state.form.capability_ids.includes(tool.capability_id);
    box.addEventListener("change", (event) => state.actions.setTool(tool.capability_id, event.target.checked));
    option.append(box, document.createTextNode(agentToolLabel(tool)));
    tools.appendChild(option);
  }
  return tools;
}

function renderEditor(state) {
  const form = state.form;
  const section = document.createElement("section");
  section.className = "agents-section";
  appendText(section, state.editing === "new" ? "New agent" : `Edit ${form.display_name}`, "h3");
  const element = document.createElement("form");
  element.className = "agents-form";

  formField(element, "Name", textControl(state, "display_name"));
  if (state.editing === "new") {
    const id = textControl(state, "profile_id");
    id.placeholder = "made from the name";
    formField(element, "ID", id, "Lowercase letters, numbers, and hyphens. Leave blank to use the name.");
  }
  formField(element, "What it is for", textControl(state, "purpose"));
  formField(element, "How it should work", textControl(state, "instructions", { multiline: true, rows: 5 }));

  const modes = document.createElement("fieldset");
  modes.className = "agents-choices";
  appendText(modes, "How it can be reached", "legend");
  for (const [mode, text] of Object.entries(INVOCATION_MODE_LABELS)) {
    const option = document.createElement("label");
    option.className = "agents-choice";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.name = `mode-${mode}`;
    box.checked = form.modes.includes(mode);
    box.addEventListener("change", (event) => state.actions.setMode(mode, event.target.checked));
    option.append(box, document.createTextNode(text));
    modes.appendChild(option);
  }
  element.appendChild(modes);

  formField(element, "Approval", selectControl(state, "approval_class", APPROVAL_LABELS));
  formField(
    element,
    "Memory it can read",
    selectControl(state, "memory_scope", MEMORY_SCOPE_LABELS),
    "Agents only read memory. What is retained follows your Memory settings.",
  );
  element.appendChild(renderToolChoices(state));
  const timeout = document.createElement("input");
  timeout.type = "number";
  timeout.name = "timeout_seconds";
  timeout.min = "1";
  timeout.max = "600";
  timeout.value = String(form.timeout_seconds);
  timeout.addEventListener("input", (event) => state.actions.setField("timeout_seconds", event.target.value));
  formField(element, "Time limit (seconds)", timeout);
  formField(
    element,
    "Runs in",
    selectControl(state, "runtime_kind", { internal: "JARVIS", acp: "An external agent" }, { rerender: true }),
    form.runtime_kind === "acp" ? "An external agent can only be run from this panel." : "",
  );
  if (form.runtime_kind === "acp") {
    formField(element, "External agent definition", textControl(state, "adapter_id"), "The ID of its ACP definition in Extensions.");
  } else {
    const stop = document.createElement("label");
    stop.className = "agents-choice";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.name = "cancellable";
    box.checked = form.cancellable;
    box.addEventListener("change", (event) => state.actions.setField("cancellable", event.target.checked));
    stop.append(box, document.createTextNode("Can be stopped while it runs"));
    element.appendChild(stop);
  }

  const buttons = document.createElement("div");
  buttons.className = "agents-buttons";
  const save = document.createElement("button");
  save.type = "submit";
  save.textContent = "Save agent";
  save.disabled = state.mutationPending;
  buttons.appendChild(save);
  const discard = document.createElement("button");
  discard.type = "button";
  discard.textContent = "Discard changes";
  discard.addEventListener("click", () => state.actions.cancelEdit());
  buttons.appendChild(discard);
  element.appendChild(buttons);
  element.addEventListener("submit", (event) => {
    event.preventDefault();
    state.actions.save();
  });
  section.appendChild(element);
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
    startDuplicate: (profileId) => controller.startDuplicate(profileId),
    startEdit: (profileId) => controller.startEdit(profileId),
    setField: (name, value, options) => controller.setField(name, value, options),
    setMode: (mode, checked) => controller.setMode(mode, checked),
    setTool: (capabilityId, checked) => controller.setTool(capabilityId, checked),
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
