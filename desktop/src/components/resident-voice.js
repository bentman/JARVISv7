import { formatValue, humanize } from "./ui/format.js";

export function createResidentVoicePresenter(options) {
  const {
    pttButton,
    voiceStatusEl,
    residentModeEl,
    residentStatusEl,
    setState,
    showError,
    appendMessage,
    syncConversation = null,
  } = options;
  let lastRenderedResidentTurnKey = "";
  const modeLabels = {
    "ptt-only": "PTT-only",
    "ptt+wake": "Wake",
    "hands-free": "Hands-free",
    continuous: "Continuous",
  };

  function boolText(value) {
    return formatValue(Boolean(value));
  }

  function valueKind(value) {
    const normalized = String(value ?? "").trim().toLowerCase();
    if (["yes", "running", "enabled", "ready", "reachable", "wake"].includes(normalized)) return "positive";
    if (["no", "stopped", "disabled", "unavailable"].includes(normalized)) return "negative";
    return "neutral";
  }

  function setModeControl(status) {
    if (!residentModeEl) return;
    const mode = status.mode || "ptt-only";
    const options = [
      ["ptt-only", true],
      ["ptt+wake", true],
      ["hands-free", true],
      ["continuous", true],
    ];
    residentModeEl.innerHTML = "";
    for (const [value, available] of options) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = modeLabels[value] || value;
      option.selected = value === mode || (mode === "ptt-only" && value === "ptt-only");
      option.disabled = value !== mode && !available;
      residentModeEl.appendChild(option);
    }
    residentModeEl.value = modeLabels[mode] ? mode : "ptt-only";
    residentModeEl.disabled = !status.ptt_supported;
    residentModeEl.title = status.ptt_supported ? "Resident voice mode" : "Resident voice mode is unavailable.";
  }

  function renderResidentModeStatus(status) {
    if (!residentStatusEl) return;
    setModeControl(status);
    const stream = status.stream || {
      present: status.stream_present,
      running: status.stream_running,
      subscribers: status.stream_subscribers,
      buffer_chunks: status.stream_buffer_chunks,
      dropped_chunks: status.stream_dropped_chunks,
      last_error: status.stream_last_error,
    };
    const degradedReasons = Array.isArray(status.degraded_reasons) ? status.degraded_reasons : [];
    const rows = [
      ["Mode", modeLabels[status.mode] || status.mode || "Unknown"],
      ["Available", boolText(status.available)],
      ["Audio stream", stream.present ? (stream.running ? "Running" : "Stopped") : "Not started"],
      ["Listeners", String(stream.subscribers ?? 0)],
      ["Dropped audio", String(stream.dropped_chunks ?? 0)],
      ["Speech detection", boolText(status.vad_configured)],
      ["Interrupt while speaking", status.barge_in_supported ? (status.barge_in_wired ? "Yes" : "Supported, not wired") : "No"],
      ["Listening for a follow-up", boolText(status.follow_up_listening)],
      ["Continuous", boolText(status.continuous_active)],
    ];
    if (status.follow_up_listening && status.follow_up_source) rows.push(["Follow-up after", humanize(status.follow_up_source)]);
    if (degradedReasons.length > 0) {
      rows.push(["Degraded", degradedReasons.join("; ")]);
    }
    residentStatusEl.replaceChildren(
      ...rows.map(([label, value]) => {
        const row = document.createElement("div");
        row.className = "resident-voice-status-field";
        const labelEl = document.createElement("span");
        const valueEl = document.createElement("span");
        labelEl.className = "resident-voice-status-label";
        labelEl.textContent = label;
        valueEl.className = "resident-voice-status-value status-value";
        valueEl.dataset.status = valueKind(value);
        valueEl.textContent = value;
        row.append(labelEl, valueEl);
        return row;
      }),
    );
    residentStatusEl.dataset.available = status.available ? "true" : "false";
    residentStatusEl.dataset.streamRunning = stream.running ? "true" : "false";
  }

  function setCaptureState(state) {
    pttButton.dataset.captureState = state;
    if (state === "processing") {
      pttButton.disabled = true;
      pttButton.setAttribute("aria-pressed", "false");
      pttButton.textContent = "Voice Running...";
      return;
    }
    pttButton.disabled = false;
    pttButton.setAttribute("aria-pressed", "false");
    pttButton.textContent = "Start Voice";
  }

  function appendResidentVoiceCompletion(status) {
    if (!status.last_transcript && !status.last_response && !status.failure_reason) return;
    const latestTurn = status.latest_turn;
    const latestTurnIsVoice = latestTurn?.input_modality === "voice";
    if (latestTurn && !latestTurnIsVoice && status.state !== "FAILED") return;
    const key = latestTurnIsVoice && latestTurn?.turn_id
      ? [latestTurn.turn_id, latestTurn.final_state ?? "", latestTurn.failure_reason ?? ""].join("|")
      : [
          status.invocation_source ?? "",
          status.state ?? "",
          status.last_transcript ?? "",
          status.last_response ?? "",
          status.failure_reason ?? "",
        ].join("|");
    if (key === lastRenderedResidentTurnKey) return;
    lastRenderedResidentTurnKey = key;
    // With a conversation feed the voice turn arrives with every other turn, attributed and deduped.
    if (syncConversation && latestTurnIsVoice) {
      syncConversation();
      return;
    }
    if (status.last_transcript) appendMessage("user", status.last_transcript);
    appendMessage("assistant", status.last_response || status.failure_reason, { search: latestTurn?.search });
  }

  function renderResidentVoiceStatus(status) {
    const state = status.state || "IDLE";
    const source = status.invocation_source || "";
    const isResidentVoice = source === "ptt" || source === "wake" || source === "barge_in" || source === "hands_free" || source === "continuous";
    if (!isResidentVoice) return;

    if (state === "LISTENING") {
      setCaptureState("processing");
      voiceStatusEl.textContent = `${source.toUpperCase()} listening`;
      setState("LISTENING");
      return;
    }
    if (["TRANSCRIBING", "REASONING", "ACTING", "RESPONDING", "SPEAKING"].includes(state)) {
      setCaptureState("processing");
      voiceStatusEl.textContent = `${source.toUpperCase()} ${state.toLowerCase()}`;
      setState(state);
      return;
    }
    if (state === "FAILED") {
      setCaptureState("idle");
      voiceStatusEl.textContent = "Voice failed";
      if (status.failure_reason) showError(status.failure_reason);
      appendResidentVoiceCompletion(status);
      return;
    }
    if (state === "IDLE") {
      setCaptureState("idle");
      voiceStatusEl.textContent = status.last_transcript || status.last_response ? "Voice complete" : "Voice idle";
      appendResidentVoiceCompletion(status);
    }
  }

  return {
    renderResidentVoiceStatus,
    renderResidentModeStatus,
    setCaptureState,
    appendResidentVoiceCompletion,
  };
}
