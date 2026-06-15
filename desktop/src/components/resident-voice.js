import { setStateLabel } from "./state-label.js";

export function createResidentVoicePresenter(options) {
  const {
    pttButton,
    voiceStatusEl,
    voiceDetailEl,
    turnStateEl,
    setState,
    showError,
    appendMessage,
  } = options;
  let lastRenderedResidentTurnKey = "";

  function setVoiceDetail(result) {
    const lines = [
      `state: ${result.state ?? ""}`,
      `source: ${result.invocation_source ?? ""}`,
      `transcript: ${result.last_transcript ?? ""}`,
      `response: ${result.last_response ?? ""}`,
      `failure_reason: ${result.failure_reason ?? ""}`,
      `tts_output_device: ${result.tts_output_device ?? ""}`,
      `turn_count: ${result.turn_count ?? 0}`,
    ];
    voiceDetailEl.textContent = lines.join("\n");
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
    const isResidentVoice = source === "ptt" || source === "wake";
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
    setCaptureState,
    appendResidentVoiceCompletion,
  };
}
