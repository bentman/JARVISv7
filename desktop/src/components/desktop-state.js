const TURN_STATE_LABELS = {
  IDLE: "IDLE",
  LISTENING: "LISTEN",
  TRANSCRIBING: "TRANSCRIBE",
  REASONING: "REASON",
  ACTING: "ACT",
  RESPONDING: "RESPOND",
  SPEAKING: "SPEAK",
  INTERRUPTED: "INTERRUPT",
  RECOVERING: "RECOVER",
  FAILED: "FAILED",
  BOOTSTRAP: "STARTING",
  STARTING: "STARTING",
  READY: "READY",
  DEGRADED: "DEGRADED",
};

const TURN_RAIL_STATES = [
  "IDLE",
  "LISTEN",
  "TRANSCRIBE",
  "REASON",
  "ACT",
  "RESPOND",
  "SPEAK",
  "INTERRUPT",
  "RECOVER",
  "FAILED",
];

const SYSTEM_STATES = {
  BOOTSTRAP: { label: "Starting", color: "degraded" },
  STARTING: { label: "Starting", color: "degraded" },
  READY: { label: "Ready", color: "ready" },
  DEGRADED: { label: "Degraded", color: "degraded" },
  FAILED: { label: "Failed", color: "failed" },
  BACKEND_UNAVAILABLE: { label: "Backend unavailable", color: "failed" },
};

function createTurnStatusRail(stateEl) {
  const rail = document.createElement("div");
  rail.className = "turn-status-rail";
  rail.id = "turn-status-card";
  rail.dataset.state = "IDLE";

  const title = document.createElement("span");
  title.className = "turn-status-title";
  title.textContent = "Turn Status";

  const labelRow = document.createElement("div");
  labelRow.className = "turn-status-labels";

  TURN_RAIL_STATES.forEach((label, index) => {
    const labelEl = document.createElement("span");
    labelEl.className = "turn-status-label";
    labelEl.dataset.label = label;
    labelEl.textContent = label;
    labelRow.appendChild(labelEl);
    if (index < TURN_RAIL_STATES.length - 1) {
      const bullet = document.createElement("span");
      bullet.className = "turn-status-separator";
      bullet.textContent = "•";
      labelRow.appendChild(bullet);
    }
  });

  rail.append(title, labelRow);
  stateEl.appendChild(rail);

  return {
    setState: (stateKey) => {
      const rawState = String(stateKey || "IDLE");
      const displayLabel = TURN_STATE_LABELS[rawState] || rawState;
      rail.dataset.state = rawState;

      for (const labelEl of labelRow.querySelectorAll(".turn-status-label")) {
        const label = labelEl.dataset.label;
        labelEl.classList.toggle("active", label === displayLabel);
      }

      return displayLabel;
    },
  };
}

export function createDesktopState(containerEl, turnStateContainerEl) {
  const systemStateEl = containerEl.querySelector("#startup-state")?.parentElement;
  const turnStatus = createTurnStatusRail(turnStateContainerEl);

  return {
    renderSystemState: (status, degraded = false) => {
      if (!systemStateEl) return;

      const rawState = String(status || "BOOTSTRAP");
      const stateInfo = SYSTEM_STATES[rawState] || { label: rawState, color: "degraded" };

      const labelEl = systemStateEl.querySelector(".label");
      if (labelEl) labelEl.textContent = "System State";

      const valueEl = systemStateEl.querySelector("strong");
      if (valueEl) {
        valueEl.textContent = stateInfo.label;
        valueEl.dataset.state = rawState;
      }

      systemStateEl.dataset.systemState = stateInfo.color;
      systemStateEl.dataset.degraded = degraded ? "true" : "false";
    },

    renderTurnStatus: (backendState, pendingState = null) => {
      const stateToUse = pendingState || backendState || "IDLE";
      turnStatus.setState(stateToUse);
    },

    setPendingState: (state) => {
      turnStatus.setState(state);
    },

    clearPendingState: () => {
      turnStatus.setState("IDLE");
    },
  };
}
