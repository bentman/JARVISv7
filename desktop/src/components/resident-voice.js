import { setStateLabel } from "./state-label.js";

export function createResidentVoicePresenter(options) {
  const {
    pttButton,
    voiceStatusEl,
    voiceDetailEl,
    residentModeEl,
    residentStatusEl,
    turnStateEl,
    setState,
    showError,
    appendMessage,
  } = options;
  let lastRenderedResidentTurnKey = "";
  const modeLabels = {
    "ptt-only": "PTT-only",
    "ptt+wake": "Wake",
    "hands-free": "Hands-free",
    continuous: "Continuous",
  };

  function setVoiceDetail(result) {
    const lines = [
      `state: ${result.state ?? ""}`,
      `source: ${result.invocation_source ?? ""}`,
      `resident_mode: ${result.resident_mode ?? result.mode ?? ""}`,
      `transcript: ${result.last_transcript ?? ""}`,
      `response: ${result.last_response ?? ""}`,
      `failure_reason: ${result.failure_reason ?? ""}`,
      `tts_output_device: ${result.tts_output_device ?? ""}`,
      `turn_count: ${result.turn_count ?? 0}`,
    ];
    voiceDetailEl.textContent = lines.join("\n");
  }

  function boolText(value) {
    return value ? "true" : "false";
  }

  function setModeControl(status) {
    if (!residentModeEl) return;
    const mode = status.mode || "ptt+wake";
    const options = [
      ["ptt-only", mode === "ptt-only" || mode === "ptt+wake"],
      ["ptt+wake", mode === "ptt+wake"],
      ["hands-free", mode === "hands-free"],
      ["continuous", mode === "continuous"],
    ];
    residentModeEl.innerHTML = "";
    for (const [value, available] of options) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = modeLabels[value] || value;
      option.selected = value === mode || (mode === "ptt+wake" && value === "ptt+wake");
      option.disabled = value !== mode && !available;
      residentModeEl.appendChild(option);
    }
    residentModeEl.value = modeLabels[mode] ? mode : "ptt+wake";
    residentModeEl.disabled = true;
    residentModeEl.title = "Backend mode changes are not exposed by this build.";
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
      ["mode", modeLabels[status.mode] || status.mode || "unknown"],
      ["available", boolText(status.available)],
      ["stream-present", boolText(stream.present)],
      ["stream", stream.running ? "running" : "stopped"],
      ["subscribers", String(stream.subscribers ?? 0)],
      ["drops", String(stream.dropped_chunks ?? 0)],
      ["vad", boolText(status.vad_configured)],
      ["barge-in", boolText(status.barge_in_supported)],
      ["barge-in-wired", boolText(status.barge_in_wired)],
    ];
    if (degradedReasons.length > 0) {
      rows.push(["degraded", degradedReasons.join("; ")]);
    }
    residentStatusEl.replaceChildren(
      ...rows.map(([label, value]) => {
        const row = document.createElement("div");
        row.className = "resident-voice-status-field";
        const labelEl = document.createElement("span");
        const valueEl = document.createElement("span");
        labelEl.className = "resident-voice-status-label";
        labelEl.textContent = label;
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
    const key = [
      status.invocation_source ?? "",
      status.last_transcript ?? "",
      status.last_response ?? "",
      status.failure_reason ?? "",
    ].join("|");
    if (key === lastRenderedResidentTurnKey) return;
    lastRenderedResidentTurnKey = key;
    if (status.last_transcript) appendMessage("user", status.last_transcript);
    appendMessage("assistant", status.last_response || status.failure_reason);
  }

  function renderResidentVoiceStatus(status) {
    setVoiceDetail(status);
    const state = status.state || "IDLE";
    setStateLabel(state, turnStateEl);
    const source = status.invocation_source || "";
    const isResidentVoice = source === "ptt" || source === "wake" || source === "barge_in";
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
