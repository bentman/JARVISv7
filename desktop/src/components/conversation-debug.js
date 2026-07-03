function pushLine(lines, label, value) {
  const text = String(value ?? "").trim();
  if (!text) return;
  lines.push(`${label}: ${text}`);
}

function shortTurnId(turnId) {
  return String(turnId || "").slice(0, 6);
}

function runtimeLine(runtimeContext) {
  const context = runtimeContext || {};
  const parts = [];
  for (const name of ["stt", "llm", "tts"]) {
    if (context[name]) parts.push(`${name}=${context[name]}`);
  }
  return parts.join(", ");
}

function captureLine(diagnostics) {
  if (!diagnostics || typeof diagnostics !== "object") return "";
  const fields = [];
  for (const name of ["source", "stage", "reason", "speech_started", "speech_chunks"]) {
    if (diagnostics[name] !== undefined && diagnostics[name] !== null && diagnostics[name] !== "") {
      fields.push(`${name}=${diagnostics[name]}`);
    }
  }
  return fields.join(", ");
}

export function renderConversationDebug(status, detailEl) {
  if (!detailEl) return;
  const lines = [];
  const latestTurn = status?.latest_turn;

  pushLine(lines, "state", status?.state || "unknown");

  if (latestTurn) {
    const source =
      latestTurn.input_modality === "voice" && status?.invocation_source
        ? status.invocation_source
        : latestTurn.input_modality || "turn";
    pushLine(
      lines,
      "turn",
      `${source} ${shortTurnId(latestTurn.turn_id)} ${latestTurn.final_state || status?.state || "unknown"}`,
    );
    pushLine(lines, "runtime", runtimeLine(latestTurn.runtime_context));
    pushLine(lines, "failure", latestTurn.failure_reason);
    if (latestTurn.degraded_reason) {
      pushLine(lines, "degraded", `tts=${latestTurn.degraded_reason}`);
    }
    pushLine(lines, "tts_output_device", latestTurn.tts_output_device);
    pushLine(lines, "artifact", latestTurn.artifact_path);
    return void (detailEl.textContent = lines.join("\n"));
  }

  pushLine(lines, "source", status?.invocation_source);
  pushLine(lines, "failure", status?.failure_reason);
  pushLine(lines, "capture", captureLine(status?.voice_capture_diagnostics));
  pushLine(lines, "turn_count", status?.turn_count ?? 0);
  detailEl.textContent = lines.join("\n");
}
