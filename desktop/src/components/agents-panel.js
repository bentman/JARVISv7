/**
 * Agents panel — agent catalog, invocation, run tracking, and cancellation.
 */

function createElement(tag, attrs = {}, text) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "className") el.className = value;
    else el.setAttribute(key, value);
  }
  if (text !== undefined) el.textContent = text;
  return el;
}

export function createAgentsPanelController(apiClient) {
  let agents = [];
  let selectedAgent = null;
  let runs = [];
  let seq = 0;

  async function loadAgents() {
    const current = ++seq;
    try {
      agents = await apiClient.listAgents();
    } catch {
      agents = [];
    }
    if (current !== seq) return;
    return agents;
  }

  async function loadRuns() {
    const current = ++seq;
    try {
      runs = await apiClient.listAgentRuns();
    } catch {
      runs = [];
    }
    if (current !== seq) return;
    return runs;
  }

  async function invokeAgent(profileId, prompt) {
    return apiClient.invokeAgent(profileId, prompt);
  }

  async function cancelAgent(profileId) {
    return apiClient.cancelAgent(profileId);
  }

  function selectAgent(profileId) {
    selectedAgent = agents.find((a) => a.profile_id === profileId) || null;
    return selectedAgent;
  }

  return {
    get agents() { return agents; },
    get selectedAgent() { return selectedAgent; },
    get runs() { return runs; },
    loadAgents,
    loadRuns,
    invokeAgent,
    cancelAgent,
    selectAgent,
  };
}

export function createAgentsPanel(controller, elements) {
  const { panel, list, detail, invokeForm, promptInput, invokeButton, runsList } = elements;

  function renderAgents() {
    list.innerHTML = "";
    for (const agent of controller.agents) {
      const item = createElement("div", { className: "agents-list-item", role: "button", tabindex: "0" });
      item.appendChild(createElement("strong", {}, agent.display_name || agent.profile_id));
      item.appendChild(createElement("span", { className: "agent-purpose" }, agent.purpose || ""));
      item.addEventListener("click", () => {
        controller.selectAgent(agent.profile_id);
        renderDetail();
      });
      list.appendChild(item);
    }
  }

  function renderDetail() {
    detail.innerHTML = "";
    const agent = controller.selectedAgent;
    if (!agent) {
      detail.appendChild(createElement("p", {}, "Select an agent to view details."));
      return;
    }
    detail.appendChild(createElement("h3", {}, agent.display_name));
    detail.appendChild(createElement("p", {}, agent.purpose || ""));
    const modes = createElement("div", { className: "agent-modes" });
    for (const mode of (agent.invocation_modes || [])) {
      modes.appendChild(createElement("span", { className: "agent-mode-badge" }, mode));
    }
    detail.appendChild(modes);
    invokeForm.style.display = agent.invocation_modes?.includes("direct") ? "block" : "none";
  }

  function renderRuns() {
    runsList.innerHTML = "";
    for (const run of controller.runs) {
      const item = createElement("div", { className: "agent-run-item" });
      item.appendChild(createElement("span", { className: `run-status run-status-${run.status}` }, run.status));
      item.appendChild(createElement("span", {}, run.agent_id || run.profile_id || "unknown"));
      if (run.error) {
        item.appendChild(createElement("span", { className: "run-error" }, run.error));
      }
      runsList.appendChild(item);
    }
    if (!controller.runs.length) {
      runsList.appendChild(createElement("p", {}, "No agent runs yet."));
    }
  }

  if (invokeButton) {
    invokeButton.addEventListener("click", async () => {
      const agent = controller.selectedAgent;
      const prompt = promptInput?.value?.trim();
      if (!agent || !prompt) return;
      invokeButton.disabled = true;
      try {
        await controller.invokeAgent(agent.profile_id, prompt);
        promptInput.value = "";
        await controller.loadRuns();
        renderRuns();
      } catch (error) {
        detail.appendChild(createElement("p", { className: "agent-error" }, String(error?.message || error)));
      } finally {
        invokeButton.disabled = false;
      }
    });
  }

  return {
    open() {
      panel.style.display = "block";
      controller.loadAgents().then(renderAgents);
      controller.loadRuns().then(renderRuns);
    },
    close() {
      panel.style.display = "none";
    },
    refresh() {
      controller.loadAgents().then(renderAgents);
      controller.loadRuns().then(renderRuns);
    },
  };
}
