import { capabilityTitle, describeAuditRecord, auditRecordState, formatActionTime, groupAuditRecords } from "./actions-panel.js";
import { ACTIVE_RUN_STATUSES, appendRunControls } from "./run-request.js";
import { confirmDestructive } from "./ui/confirm.js";
import { appendText, button, buttonRow, details, facts, field, option, statusBadge } from "./ui/dom.js";
import { errorMessage, isConflict, statusState, statusText } from "./ui/format.js";
import { createPanelLifecycle, messageRegion, renderPanelHeader, section, sectionState } from "./ui/panel.js";
import { VERB } from "./ui/vocabulary.js";

const AGENT_CAPABILITY_PREFIX = "agent-invoke-";

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

export const CONNECTION_TEST_PROMPT = "Connection test from JARVIS. Reply with the single word: ready.";

// The newest invocation of an agent, read from its capability audit (newest first). While a run
// is in flight its proposal has no execution result or cancellation yet; that proposal id is what
// targets a specific run for cancellation and links it to its external-agent run.
export function agentProposalId(records, profileId, { unfinished = false } = {}) {
  const capabilityId = `${AGENT_CAPABILITY_PREFIX}${profileId}`;
  const finished = new Set((records || [])
    .filter((record) => record.kind === "execution_result" || record.kind === "action_cancellation")
    .map((record) => record.proposal_id));
  const proposal = (records || []).find((record) => record.capability_id === capabilityId
    && record.kind === "action_proposal"
    && !(unfinished && finished.has(record.proposal_id)));
  return proposal?.proposal_id || "";
}

// An ACP agent's reply arrives as streamed agent_message_chunk session updates on its run, not
// in the prompt response, which carries only the stop reason.
export function acpMessageText(events) {
  let text = "";
  for (const event of events || []) {
    const update = event?.update;
    const kind = update?.sessionUpdate || update?.session_update;
    if (event?.kind === "session_update" && kind === "agent_message_chunk" && typeof update.content?.text === "string") {
      text += update.content.text;
    }
  }
  return text.trim();
}

export function agentOutputText(payload, linkedRun = null) {
  const response = payload?.output?.response;
  if (typeof response === "string" && response.trim()) return response.trim();
  return acpMessageText(linkedRun?.events);
}

export function acpDefinitionId(extension) {
  return String(extension?.extension_id || "").replace(/^acp:/, "");
}

export function acpDefinitionStatus(extension, runtime = null) {
  if (!extension) return "Not found in Extensions";
  if (extension.state === "disabled") return "Disabled in Extensions";
  if (extension.state === "retired") return "Retired";
  if (extension.availability !== "available") return "Unavailable";
  if (extension.readiness === "degraded") return "Degraded";
  if (extension.readiness === "unavailable") return "Not ready";
  if (runtime?.connected === true) return "Ready · connected";
  return "Ready";
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
    return "Choose the external agent definition it runs in.";
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

export function createHandoffStatus({ label, endButton, openButton = null, openAgent = null, endHandoff, onEnded, onError }) {
  let sessionId = "";
  let agentId = "";
  openButton?.addEventListener("click", () => {
    if (agentId) openAgent?.(agentId);
  });
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
      agentId = activeAgent?.profile_id || "";
      if (openButton) openButton.hidden = !activeAgent || !openAgent;
      endButton.disabled = false;
    },
  };
}

function copyState(state) {
  return {
    ...state,
    agents: [...state.agents],
    runs: [...state.runs],
    problems: [...state.problems],
    acpDefinitions: [...state.acpDefinitions],
    runtimes: { ...state.runtimes },
    extensionRuns: [...state.extensionRuns],
    pendingApprovals: [...state.pendingApprovals],
    activeRun: state.activeRun ? { ...state.activeRun } : null,
    lastResult: state.lastResult ? { ...state.lastResult } : null,
    test: state.test ? { ...state.test } : null,
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
    problems: [],
    acpDefinitions: [],
    acpError: "",
    runtimes: {},
    extensionRuns: [],
    pendingApprovals: [],
    invokePending: false,
    activeRun: null,
    lastResult: null,
    test: null,
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
      state.problems = payload?.problems || [];
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

  // A quiet refresh is a poll during a live run: it must not flash the list into its loading state.
  async function refreshRuns({ quiet = false } = {}) {
    if (!handlers.listAgentRuns) return null;
    const request = ++runsSequence;
    if (!quiet) {
      state.runsLoading = true;
      state.runsError = "";
      emit();
    }
    try {
      const payload = await handlers.listAgentRuns();
      if (request !== runsSequence) return null;
      state.runs = payload?.records || [];
      state.runsError = "";
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

  async function refreshAcpDefinitions() {
    if (!handlers.getExtensions) return;
    try {
      const payload = await handlers.getExtensions();
      state.acpDefinitions = (payload?.extensions || []).filter((extension) => extension.family === "acp");
      state.acpError = "";
    } catch (error) {
      state.acpError = errorMessage(error, "External agent definitions are unavailable.");
    }
    emit();
  }

  async function refreshRuntime(adapterId) {
    if (!handlers.getExtensionRuntime || !adapterId) return null;
    try {
      const runtime = await handlers.getExtensionRuntime(`acp:${adapterId}`);
      state.runtimes = { ...state.runtimes, [adapterId]: runtime };
      return runtime;
    } catch (error) {
      state.runtimes = { ...state.runtimes, [adapterId]: { error: errorMessage(error, "Its status is unavailable.") } };
      return null;
    } finally {
      emit();
    }
  }

  async function refreshExtensionRuns() {
    if (!handlers.getExtensionRuns) return;
    try {
      const payload = await handlers.getExtensionRuns();
      state.extensionRuns = (payload?.runs || []).filter((run) => String(run.extension_id || "").startsWith("acp:"));
    } catch {
      // Keep the last known runs; the agent audit remains the record of what happened.
    }
  }

  async function refreshPendingApprovals() {
    if (!handlers.getPendingActions) return;
    try {
      state.pendingApprovals = (await handlers.getPendingActions())?.pending || [];
    } catch (error) {
      state.mutationError = errorMessage(error, "Pending approvals are unavailable.");
    }
  }

  function selectedAcpAdapter() {
    const agent = agentById(state.selectedProfileId);
    return agent?.runtime?.kind === "acp" ? agent.runtime.adapter_id : "";
  }

  function selectAgent(profileId) {
    state.selectedProfileId = profileId;
    state.notice = "";
    state.mutationError = "";
    emit();
    const adapterId = selectedAcpAdapter();
    if (adapterId) {
      refreshRuntime(adapterId);
      refreshExtensionRuns().then(emit);
    }
  }

  function hasLiveRun() {
    const adapterId = selectedAcpAdapter();
    return state.invokePending
      || Boolean(state.test?.pending)
      || Boolean(adapterId && state.extensionRuns.some((run) => run.extension_id === `acp:${adapterId}` && ACTIVE_RUN_STATUSES.includes(run.status)));
  }

  async function poll() {
    await Promise.all([refreshRuns({ quiet: true }), refreshExtensionRuns()]);
    if (state.activeRun && !state.activeRun.proposalId) {
      state.activeRun = { ...state.activeRun, proposalId: agentProposalId(state.runs, state.activeRun.profileId, { unfinished: true }) };
    }
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
      if (isConflict(error)) {
        // Someone else changed the profile since it was read; show what is current now.
        state.mutationError = `${state.mutationError} The agent list was reloaded.`;
        await refreshAgents();
      }
      return null;
    } finally {
      state.mutationPending = false;
      emit();
    }
  }

  // An invocation holds its own pending flag rather than the shared mutation lock, so the run can
  // still be cancelled, and its permission or input requests answered, while it is in flight.
  async function invoke(profileId, prompt) {
    if (state.invokePending) return null;
    state.invokePending = true;
    state.activeRun = { profileId, proposalId: "" };
    state.lastResult = null;
    state.notice = "";
    state.mutationError = "";
    emit();
    let payload = null;
    try {
      payload = await handlers.invokeAgent(profileId, prompt);
      state.notice = agentInvokeNotice(payload);
      state.prompt = "";
      if (payload?.status === "awaiting_approval") await refreshPendingApprovals();
      return payload;
    } catch (error) {
      state.mutationError = errorMessage(error, "The agent could not be run.");
      return null;
    } finally {
      const knownProposalId = state.activeRun?.proposalId || "";
      state.invokePending = false;
      state.activeRun = null;
      const agent = agentById(profileId);
      await Promise.all([
        refreshRuns({ quiet: true }),
        refreshExtensionRuns(),
        agent?.runtime?.kind === "acp" ? refreshRuntime(agent.runtime.adapter_id) : null,
      ]);
      if (payload) {
        state.lastResult = { profileId, proposalId: knownProposalId || agentProposalId(state.runs, profileId), payload };
      }
      emit();
    }
  }

  async function cancel(profileId, confirm = async () => true) {
    if (!(await confirm("Cancel this agent run?"))) return null;
    const proposalId = state.activeRun?.profileId === profileId ? state.activeRun.proposalId : "";
    if (proposalId && handlers.cancelAction) {
      return mutate(() => handlers.cancelAction(proposalId), (payload) => agentCancelNotice(payload));
    }
    return mutate(() => handlers.cancelAgent(profileId), agentCancelNotice);
  }

  async function decide(proposalId, outcome) {
    if (!handlers.decideAction) return null;
    const payload = await mutate(
      () => handlers.decideAction(proposalId, outcome, null),
      () => (outcome === "approved" ? "Approved." : "Declined."),
    );
    await Promise.all([refreshPendingApprovals(), refreshExtensionRuns()]);
    emit();
    return payload;
  }

  async function answer(runId, requestId, answerValue) {
    if (!handlers.answerExtensionInput) return;
    try {
      await handlers.answerExtensionInput(runId, requestId, answerValue);
      state.notice = answerValue?.action === "decline" ? "Request declined." : "Answer sent.";
    } catch (error) {
      state.mutationError = errorMessage(error, "The answer was not accepted.");
    }
    await refreshExtensionRuns();
    emit();
  }

  async function cancelLinkedRun(proposalId, confirm = async () => true) {
    if (!handlers.cancelAction) return null;
    if (!(await confirm("Cancel this external agent run?"))) return null;
    return mutate(() => handlers.cancelAction(proposalId), agentCancelNotice);
  }

  function notice(message) {
    state.notice = message;
    emit();
  }

  function testMessage(result, run) {
    const status = result?.status;
    if (status === "success") {
      const text = acpMessageText(run?.events);
      return text ? `Connected. It replied: ${text}` : "Connected. It answered with no text.";
    }
    if (status === "awaiting_approval") return "The test is waiting for approval.";
    if (status === "outcome_unknown") return "The test outcome is unknown; the agent may not have answered.";
    return `The test failed: ${result?.execution?.error || run?.error || status || "no result was returned"}.`;
  }

  // A connection test sends one short prompt through the definition's own prompt operation: it
  // proves the process starts, the protocol session opens, and the agent answers.
  async function testConnection(adapterId) {
    if (!handlers.getExtensionRuntime || !handlers.invokeExtension || state.test?.pending) return null;
    const extensionId = `acp:${adapterId}`;
    state.test = { adapterId, pending: true, ok: false, message: "" };
    emit();
    let ok = false;
    let message;
    try {
      const runtime = await refreshRuntime(adapterId);
      const operation = (runtime?.operations || []).find((item) => item.name === "prompt");
      if (!operation) {
        throw new Error(runtime?.unavailable_reason || "This definition cannot be prompted. Check that it is enabled and valid in Extensions.");
      }
      const result = await handlers.invokeExtension(extensionId, operation.capability_id, { prompt: CONNECTION_TEST_PROMPT });
      await refreshExtensionRuns();
      const run = state.extensionRuns.find((item) => item.extension_id === extensionId
        && (!result?.proposal_id || item.proposal_id === result.proposal_id));
      ok = result?.status === "success";
      message = testMessage(result, run);
    } catch (error) {
      message = errorMessage(error, "The connection test failed.");
    }
    state.test = { adapterId, pending: false, ok, message };
    await refreshRuntime(adapterId);
    return ok;
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
    return Promise.all([refreshTools(), refreshAcpDefinitions()]);
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
      const adapterId = selectedAcpAdapter();
      if (adapterId) await refreshRuntime(adapterId);
    }
    return payload;
  }

  async function remove(profileId, confirm = async () => true) {
    const agent = agentById(profileId);
    if (!agent?.editable) return null;
    if (!(await confirm(`Delete the agent "${agent.display_name || profileId}"? This can't be undone.`))) return null;
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
    await Promise.all([refreshAgents(), refreshRuns(), refreshAcpDefinitions(), refreshExtensionRuns()]);
    const adapterId = selectedAcpAdapter();
    if (adapterId) await refreshRuntime(adapterId);
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
    decide,
    answer,
    cancelLinkedRun,
    notice,
    testConnection,
    refreshRuntime,
    hasLiveRun,
    poll,
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

function acpDefinition(state, adapterId) {
  return state.acpDefinitions.find((extension) => acpDefinitionId(extension) === adapterId) || null;
}

const RUN_CONTROL_ACTIONS = (state) => ({
  answer: (runId, requestId, answerValue) => state.actions.answer(runId, requestId, answerValue),
  decide: (proposalId, outcome) => state.actions.decide(proposalId, outcome),
  cancel: (proposalId) => state.actions.cancelLinkedRun(proposalId),
  notice: (message) => state.actions.notice(message),
});

function renderExternalAgent(state, agent) {
  const adapterId = agent.runtime.adapter_id;
  const extension = acpDefinition(state, adapterId);
  const runtime = state.runtimes[adapterId] || null;
  const block = document.createElement("div");
  block.className = "agents-external";
  appendText(block, "External agent", "h4");
  const entries = [["Definition", extension?.display_name || adapterId], ["Status", acpDefinitionStatus(extension, runtime)]];
  if (runtime && !runtime.error) entries.push(["Connected now", runtime.connected === true]);
  block.appendChild(facts(entries));
  if (state.acpError) appendText(block, state.acpError, "p", "panel-error");
  if (runtime?.error) appendText(block, runtime.error, "p", "panel-error");
  const testing = state.test?.adapterId === adapterId ? state.test : null;
  block.appendChild(buttonRow(button(testing?.pending ? "Testing…" : "Test connection", {
    focusKey: `agent:${agent.profile_id}:test`,
    onClick: () => state.actions.testConnection(adapterId),
    disabled: Boolean(testing?.pending) || !extension,
  })));
  if (testing?.message) appendText(block, testing.message, "p", testing.ok ? "panel-notice" : "panel-error");

  const runs = state.extensionRuns.filter((run) => run.extension_id === `acp:${adapterId}`).slice(0, 3);
  for (const run of runs) {
    const item = document.createElement("div");
    item.className = "panel-inset";
    item.appendChild(statusBadge(`${formatActionTime(run.started_at)} · ${statusText(run.status)}`, statusState(run.status)));
    const text = acpMessageText(run.events);
    if (text) appendText(item, text, "p", "agents-output");
    if (run.error) appendText(item, run.error, "p", "panel-error");
    appendRunControls(item, run, RUN_CONTROL_ACTIONS(state));
    item.appendChild(details([["Run", run.run_id], ["Proposal", run.proposal_id]], { events: run.events, result: run.result }));
    block.appendChild(item);
  }
  return block;
}

// The approvals an agent is waiting on: its own invocation, or an action it proposed itself.
export function agentPendingApprovals(pending, profileId) {
  return (pending || []).filter((item) => item.capability_id === `${AGENT_CAPABILITY_PREFIX}${profileId}`
    || item.proposed_by === `agent:${profileId}`);
}

function renderPendingApprovals(state, approvals) {
  const block = document.createElement("div");
  block.className = "agents-approvals";
  appendText(block, "Waiting for your approval", "h4");
  for (const pending of approvals) {
    const row = document.createElement("div");
    appendText(row, `${pending.label || capabilityTitle(pending.capability_id)}: ${pending.reason}`, "p", "panel-help");
    row.appendChild(buttonRow(
      button(VERB.approve, {
        variant: "primary",
        focusKey: `approval:${pending.proposal_id}:approved`,
        onClick: () => state.actions.decide(pending.proposal_id, "approved"),
        disabled: state.mutationPending,
      }),
      button(VERB.decline, {
        focusKey: `approval:${pending.proposal_id}:denied`,
        onClick: () => state.actions.decide(pending.proposal_id, "denied"),
        disabled: state.mutationPending,
      }),
    ));
    row.appendChild(details([["Capability", pending.capability_id], ["Proposal", pending.proposal_id]], pending.arguments));
    block.appendChild(row);
  }
  return block;
}

function renderLastResult(state, agent) {
  const result = state.lastResult;
  const block = document.createElement("div");
  block.className = "agents-result";
  appendText(block, "Last run", "h4");
  const payload = result.payload || {};
  const linked = state.extensionRuns.find((run) => run.proposal_id && run.proposal_id === result.proposalId) || null;
  const status = appendText(block, agentInvokeNotice(payload), "p", "agents-status");
  status.dataset.state = agentRunActivityState({ record: { status: payload.status } });
  const text = agentOutputText(payload, linked);
  if (text) appendText(block, text, "p", "agents-output");
  if (payload.error) appendText(block, payload.error, "p", "panel-error");
  block.appendChild(details([
    ["Agent", agent.profile_id],
    ["Proposal", result.proposalId],
    ["Turn", payload.turn_id],
    ["Session", payload.session_id],
  ], payload.output));
  return block;
}

function selectedAgent(state) {
  return state.agents.find((agent) => agent.profile_id === state.selectedProfileId) || null;
}

function renderCatalog(state) {
  const node = section("Agents");
  node.appendChild(buttonRow(button("New agent", {
    variant: "primary",
    focusKey: "agents:new",
    onClick: () => state.actions.startCreate(),
    disabled: state.mutationPending || Boolean(state.editing),
  })));
  if (sectionState(node, { loading: state.agentsLoading, error: state.agentsError, thing: "agents" })) return node;
  for (const problem of state.problems) {
    const row = document.createElement("div");
    appendText(row, `Could not load ${capabilityTitle(problem.capability_id).replace(/^Run agent /, "")}: ${problem.reason}`, "p", "panel-error");
    row.appendChild(details([["Capability", problem.capability_id]]));
    node.appendChild(row);
  }
  if (sectionState(node, { empty: !state.agents.length, thing: "agents" })) return node;
  const list = document.createElement("ul");
  list.className = "panel-list";
  for (const agent of state.agents) {
    const item = document.createElement("li");
    const row = document.createElement("button");
    row.type = "button";
    row.className = "agents-row";
    row.dataset.focusKey = `agent:${agent.profile_id}`;
    row.setAttribute("aria-pressed", agent.profile_id === state.selectedProfileId ? "true" : "false");
    appendText(row, agent.display_name || agent.profile_id, "strong");
    appendText(row, agent.purpose, "span", "panel-help");
    appendText(row, agentModesSummary(agent.invocation_modes), "span", "panel-help");
    if (agent.enabled === false) appendText(row, "Disabled", "span", "panel-help");
    row.addEventListener("click", () => state.actions.selectAgent(agent.profile_id));
    item.appendChild(row);
    list.appendChild(item);
  }
  node.appendChild(list);
  return node;
}

function renderDetail(state) {
  const node = section("Agent detail");
  const agent = selectedAgent(state);
  if (!agent) {
    appendText(node, "Select an agent to see what it does and how it runs.", "p", "panel-help");
    return node;
  }
  appendText(node, agent.display_name || agent.profile_id, "strong");
  appendText(node, agent.purpose, "p", "panel-help");
  node.appendChild(facts([
    ["Reached by", agentModesSummary(agent.invocation_modes)],
    ["Approval", APPROVAL_LABELS[agent.approval_class] || agent.approval_class],
    ["Memory it can read", MEMORY_SCOPE_LABELS[agent.memory_scope] || agent.memory_scope],
    ["Tools it may use", agent.capability_ids?.length ? `${agent.capability_ids.length} allowed` : "None"],
    ["Can be stopped", agent.cancellable],
    ["Runs in", agentRuntimeLabel(agent.runtime, acpDefinition(state, agent.runtime?.adapter_id))],
    ["Owner", agent.editable ? "You (editable)" : "Built in (duplicate it to change it)"],
    ["Enabled", agent.enabled !== false],
  ]));

  if (agent.enabled === false) {
    appendText(node, "This agent is disabled. Enable it to run it.", "p", "panel-help");
  } else if (!agent.invocation_modes?.includes("direct")) {
    appendText(node, "This agent can't be run directly from this panel.", "p", "panel-help");
  } else {
    const form = document.createElement("form");
    form.className = "agents-invoke";
    const prompt = document.createElement("textarea");
    prompt.name = "prompt";
    prompt.required = true;
    prompt.value = state.prompt;
    prompt.dataset.focusKey = `agent:${agent.profile_id}:prompt`;
    // The prompt draft lives in controller state so a run refresh does not discard it, and it is
    // not re-emitted on input so typing never re-renders the textarea out from under the caret.
    prompt.addEventListener("input", (event) => state.actions.setPrompt(event.target.value));
    form.appendChild(field("Prompt", prompt));
    form.appendChild(buttonRow(button(state.invokePending ? "Running…" : "Invoke agent", {
      type: "submit",
      focusKey: `agent:${agent.profile_id}:invoke`,
      disabled: state.invokePending,
    })));
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!agentInvokeEnabled(agent, prompt.value, state.invokePending)) return;
      state.actions.setPrompt(prompt.value);
      state.actions.invoke(agent.profile_id, prompt.value);
    });
    node.appendChild(form);
  }
  if (state.lastResult?.profileId === agent.profile_id) node.appendChild(renderLastResult(state, agent));
  const approvals = agentPendingApprovals(state.pendingApprovals, agent.profile_id);
  if (approvals.length) node.appendChild(renderPendingApprovals(state, approvals));
  if (agent.runtime?.kind === "acp") node.appendChild(renderExternalAgent(state, agent));

  const enabled = agent.enabled !== false;
  node.appendChild(buttonRow(
    button(VERB.cancelRun, {
      focusKey: `agent:${agent.profile_id}:cancel`,
      onClick: () => state.actions.cancel(agent.profile_id),
      disabled: !agent.cancellable || state.mutationPending
        || (state.invokePending && state.activeRun?.profileId !== agent.profile_id),
      title: agent.cancellable ? "" : "This agent profile is not cancellable.",
    }),
    button(enabled ? VERB.disable : VERB.enable, {
      focusKey: `agent:${agent.profile_id}:toggle`,
      onClick: () => state.actions.setEnabled(agent.profile_id, !enabled),
      disabled: state.mutationPending || state.invokePending,
    }),
    agent.editable
      ? button("Edit profile", {
        focusKey: `agent:${agent.profile_id}:edit`,
        onClick: () => state.actions.startEdit(agent.profile_id),
        disabled: state.mutationPending || Boolean(state.editing),
      })
      : button("Duplicate as my agent", {
        focusKey: `agent:${agent.profile_id}:duplicate`,
        onClick: () => state.actions.startDuplicate(agent.profile_id),
        disabled: state.mutationPending || Boolean(state.editing),
      }),
    agent.editable
      ? button(VERB.delete, {
        variant: "danger",
        focusKey: `agent:${agent.profile_id}:delete`,
        onClick: () => state.actions.remove(agent.profile_id),
        disabled: state.mutationPending || state.invokePending,
      })
      : null,
  ));
  return node;
}

function agentRuntimeLabel(runtime, definition = null) {
  if (runtime?.kind === "acp") return `External agent (${definition?.display_name || runtime.adapter_id})`;
  return "JARVIS";
}

function formField(parent, labelText, control, help = "") {
  parent.appendChild(field(labelText, control, { help }));
  return control;
}

function textControl(state, name, { multiline = false, rows = 3 } = {}) {
  const control = document.createElement(multiline ? "textarea" : "input");
  if (multiline) control.rows = rows;
  else control.type = "text";
  control.name = name;
  control.value = state.form[name];
  control.dataset.focusKey = `agent-form:${name}`;
  control.addEventListener("input", (event) => state.actions.setField(name, event.target.value));
  return control;
}

function selectControl(state, name, labels, { rerender = false } = {}) {
  const control = document.createElement("select");
  control.name = name;
  control.dataset.focusKey = `agent-form:${name}`;
  for (const [value, text] of Object.entries(labels)) control.appendChild(option(value, text, state.form[name] === value));
  control.addEventListener("change", (event) => state.actions.setField(name, event.target.value, { rerender }));
  return control;
}

function acpDefinitionPicker(state) {
  const control = document.createElement("select");
  control.name = "adapter_id";
  control.dataset.focusKey = "agent-form:adapter_id";
  const choices = [["", "Choose a definition…"]];
  for (const extension of state.acpDefinitions) {
    choices.push([acpDefinitionId(extension), `${extension.display_name || acpDefinitionId(extension)} (${acpDefinitionStatus(extension)})`]);
  }
  // A saved definition that no longer exists stays selectable, so an edit never drops it silently.
  const current = state.form.adapter_id;
  if (current && !choices.some(([value]) => value === current)) choices.push([current, `${current} (${acpDefinitionStatus(null)})`]);
  for (const [value, text] of choices) control.appendChild(option(value, text, current === value));
  control.addEventListener("change", (event) => state.actions.setField("adapter_id", event.target.value));
  return control;
}

function choice(name, checked, text, onChange) {
  const label = document.createElement("label");
  label.className = "panel-choice";
  const box = document.createElement("input");
  box.type = "checkbox";
  box.name = name;
  box.checked = checked;
  box.dataset.focusKey = `agent-form:${name}`;
  box.addEventListener("change", (event) => onChange(event.target.checked));
  label.append(box, document.createTextNode(text));
  return label;
}

function renderToolChoices(state) {
  const tools = document.createElement("fieldset");
  tools.className = "panel-choices";
  appendText(tools, "Tools it may use", "legend");
  const known = new Set(state.tools.map((tool) => tool.capability_id));
  // A tool already allowed but no longer offered stays listed, so saving never drops it silently.
  const choices = [
    ...state.tools,
    ...state.form.capability_ids
      .filter((id) => !known.has(id))
      .map((id) => ({ capability_id: id, label: id, needs_approval: false, available: false })),
  ];
  if (state.toolsError) appendText(tools, state.toolsError, "p", "panel-error");
  if (!choices.length) {
    appendText(tools, "No tools are available. Add them in Extensions.", "p", "panel-help");
    return tools;
  }
  for (const tool of choices) {
    tools.appendChild(choice(
      `tool-${tool.capability_id}`,
      state.form.capability_ids.includes(tool.capability_id),
      agentToolLabel(tool),
      (checked) => state.actions.setTool(tool.capability_id, checked),
    ));
  }
  return tools;
}

function renderEditor(state) {
  const form = state.form;
  const node = section(state.editing === "new" ? "New agent" : `Edit ${form.display_name}`);
  const element = document.createElement("form");
  element.className = "panel-form";

  formField(element, "Name", textControl(state, "display_name"));
  if (state.editing === "new") {
    const id = textControl(state, "profile_id");
    id.placeholder = "made from the name";
    formField(element, "ID", id, "Lowercase letters, numbers, and hyphens. Leave blank to use the name.");
  }
  formField(element, "What it is for", textControl(state, "purpose"));
  formField(element, "How it should work", textControl(state, "instructions", { multiline: true, rows: 5 }));

  const modes = document.createElement("fieldset");
  modes.className = "panel-choices";
  appendText(modes, "How it can be reached", "legend");
  for (const [mode, text] of Object.entries(INVOCATION_MODE_LABELS)) {
    modes.appendChild(choice(`mode-${mode}`, form.modes.includes(mode), text, (checked) => state.actions.setMode(mode, checked)));
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
  timeout.dataset.focusKey = "agent-form:timeout_seconds";
  timeout.addEventListener("input", (event) => state.actions.setField("timeout_seconds", event.target.value));
  formField(element, "Time limit (seconds)", timeout);
  formField(
    element,
    "Runs in",
    selectControl(state, "runtime_kind", { internal: "JARVIS", acp: "An external agent" }, { rerender: true }),
    form.runtime_kind === "acp" ? "An external agent can only be run from this panel." : "",
  );
  if (form.runtime_kind === "acp") {
    formField(
      element,
      "External agent definition",
      acpDefinitionPicker(state),
      state.acpDefinitions.length ? "Definitions are added and edited in Extensions." : "No external agent definitions exist yet. Add one in Extensions.",
    );
    if (state.acpError) appendText(element, state.acpError, "p", "panel-error");
  } else {
    element.appendChild(choice("cancellable", form.cancellable, "Can be stopped while it runs",
      (checked) => state.actions.setField("cancellable", checked)));
  }

  element.appendChild(buttonRow(
    button("Save agent", { type: "submit", disabled: state.mutationPending, focusKey: "agent-form:save" }),
    button(VERB.discard, { onClick: () => state.actions.cancelEdit(), focusKey: "agent-form:discard" }),
  ));
  element.addEventListener("submit", (event) => {
    event.preventDefault();
    state.actions.save();
  });
  node.appendChild(element);
  return node;
}

function renderRuns(state) {
  const node = section("Runs");
  if (sectionState(node, { loading: state.runsLoading, error: state.runsError, thing: "agent runs" })) return node;
  if (!state.runs.length) {
    appendText(node, "No agent runs have been recorded.", "p", "panel-help");
    return node;
  }
  const names = new Map(state.agents.map((agent) => [agent.profile_id, agent.display_name || agent.profile_id]));
  const list = document.createElement("ul");
  list.className = "panel-list";
  for (const group of groupAuditRecords(state.runs)) {
    const item = document.createElement("li");
    const profileId = agentRunProfileId({ capability_id: group.capabilityId });
    appendText(item, names.get(profileId) || profileId || capabilityTitle(group.capabilityId), "strong");
    const steps = document.createElement("ol");
    steps.className = "actions-audit-steps";
    for (const record of group.records) {
      const step = appendText(steps, `${formatActionTime(record.recorded_at)} · ${describeAuditRecord(record)}`, "li", "agents-status");
      step.dataset.state = auditRecordState(record);
    }
    item.appendChild(steps);
    item.appendChild(details([["Capability", group.capabilityId], ["Proposal", group.proposalId]], group.records));
    list.appendChild(item);
  }
  node.appendChild(list);
  return node;
}

function renderPanel(state) {
  return [
    renderPanelHeader("Agents"),
    messageRegion({ notice: state.notice, error: state.mutationError }),
    renderCatalog(state),
    state.editing ? renderEditor(state) : renderDetail(state),
    renderRuns(state),
  ];
}

export function createAgentsPanel(container, handlers, options = {}) {
  const confirm = options.confirmDestructive || confirmDestructive;
  let controller;
  const actions = {
    selectAgent: (profileId) => controller.selectAgent(profileId),
    setPrompt: (value) => controller.setPrompt(value),
    invoke: (profileId, prompt) => controller.invoke(profileId, prompt),
    cancel: (profileId) => controller.cancel(profileId, confirm),
    decide: (proposalId, outcome) => controller.decide(proposalId, outcome),
    answer: (runId, requestId, answerValue) => controller.answer(runId, requestId, answerValue),
    cancelLinkedRun: (proposalId) => controller.cancelLinkedRun(proposalId, confirm),
    notice: (message) => controller.notice(message),
    testConnection: (adapterId) => controller.testConnection(adapterId),
    startCreate: () => controller.startCreate(),
    startDuplicate: (profileId) => controller.startDuplicate(profileId),
    startEdit: (profileId) => controller.startEdit(profileId),
    setField: (name, value, fieldOptions) => controller.setField(name, value, fieldOptions),
    setMode: (mode, checked) => controller.setMode(mode, checked),
    setTool: (capabilityId, checked) => controller.setTool(capabilityId, checked),
    cancelEdit: () => controller.cancelEdit(),
    save: () => controller.save(),
    remove: (profileId) => controller.remove(profileId, confirm),
    setEnabled: (profileId, enabled) => controller.setEnabled(profileId, enabled),
  };
  // A live run streams progress and may stop to ask for permission or input, so the panel
  // follows it while one is in flight.
  const lifecycle = createPanelLifecycle(container, {
    load: () => controller.load(),
    render: (state) => renderPanel({ ...state, actions }),
    cancelPendingReads: () => controller.cancelPendingReads(),
    onClose: options.onClose,
    poll: { active: () => controller.hasLiveRun(), run: () => controller.poll() },
  });
  controller = createAgentsPanelController(handlers, lifecycle.draw);
  return { open: lifecycle.open, close: lifecycle.close, isOpen: lifecycle.isOpen, controller };
}
