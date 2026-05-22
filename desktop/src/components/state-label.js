const STATE_LABELS = {
  BOOTSTRAP: "Starting",
  STARTING: "Starting",
  READY: "Ready",
  IDLE: "Ready",
  LISTENING: "Listening",
  TRANSCRIBING: "Transcribing",
  REASONING: "Thinking",
  ACTING: "Acting",
  RESPONDING: "Responding",
  SPEAKING: "Speaking",
  INTERRUPTED: "Interrupted",
  RECOVERING: "Recovering",
  DEGRADED: "Degraded",
  FAILED: "Failed",
};

export function setStateLabel(stateKey, labelEl) {
  if (!labelEl) return;

  const rawState = String(stateKey || "UNKNOWN");
  labelEl.textContent = STATE_LABELS[rawState] || rawState;
  labelEl.dataset.state = rawState;
}