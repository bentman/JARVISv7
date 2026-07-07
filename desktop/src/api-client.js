function parseJson(value) {
  return JSON.parse(value);
}

function parseBackendStartupError(error) {
  const message = String(error?.message || error || "");
  try {
    const payload = JSON.parse(message);
    if (payload && typeof payload === "object") return payload;
  } catch {
    // Fall through to line-oriented diagnostics parsed from legacy error text.
  }
  const diagnostics = {};
  for (const line of message.split(/\r?\n/)) {
    const match = line.match(/^(python|script|working_directory|host|port|stdout_log|stderr_log)=(.*)$/);
    if (!match) continue;
    const key = match[1] === "script" ? "backend_script_path" : match[1] === "python" ? "python_path" : match[1];
    diagnostics[key] = match[2].trim();
  }
  return { failure: message.split(/\r?\n/)[0] || "backend startup failed", diagnostics };
}

function backendStartupError(error) {
  const payload = parseBackendStartupError(error);
  const wrapped = new Error(payload.failure || "backend startup failed");
  wrapped.diagnostics = payload;
  return wrapped;
}

export function createApiClient(invoke) {
  if (!invoke) return null;

  return {
    startBackend: async () => {
      try {
        return parseJson(await invoke("start_backend"));
      } catch (error) {
        throw backendStartupError(error);
      }
    },
    stopBackend: () => invoke("stop_backend"),
    getReadiness: async () => parseJson(await invoke("get_readiness")),
    getSessionStatus: async () => parseJson(await invoke("get_session_status")),
    invokeResidentPtt: async () => parseJson(await invoke("invoke_resident_ptt")),
    getWakeStatus: async () => parseJson(await invoke("get_wake_status")),
    getResidentVoiceStatus: async () => parseJson(await invoke("get_resident_voice_status")),
    startResidentVoiceStream: async () => parseJson(await invoke("start_resident_voice_stream")),
    stopResidentVoiceStream: async () => parseJson(await invoke("stop_resident_voice_stream")),
    startWakeMonitor: async () => parseJson(await invoke("start_wake_monitor")),
    stopWakeMonitor: () => invoke("stop_wake_monitor"),
    toggleWakeMonitor: async () => parseJson(await invoke("toggle_wake_monitor")),
    setResidentVoiceMode: async (mode) => parseJson(await invoke("set_resident_voice_mode", { mode })),
    setResidentVoiceTtsVoice: async (voice) => parseJson(await invoke("set_resident_voice_tts_voice", { voice })),
    getPersonalityList: async () => parseJson(await invoke("get_personality_list")),
    selectPersonality: async (profileId) => parseJson(await invoke("select_personality", { profileId })),
    getOperatorConfig: async () => parseJson(await invoke("get_operator_config")),
    writeOperatorConfig: async (fields) => parseJson(await invoke("write_operator_config", { fields })),
    submitText: async (text) => parseJson(await invoke("submit_text", { text })),
  };
}
