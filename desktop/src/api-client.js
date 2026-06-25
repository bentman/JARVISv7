export function createApiClient(invoke) {
  if (!invoke) return null;

  return {
    startBackend: async () => JSON.parse(await invoke("start_backend")),
    stopBackend: () => invoke("stop_backend"),
    getReadiness: async () => JSON.parse(await invoke("get_readiness")),
    getSessionStatus: async () => JSON.parse(await invoke("get_session_status")),
    invokeResidentPtt: async () => JSON.parse(await invoke("invoke_resident_ptt")),
    getWakeStatus: async () => JSON.parse(await invoke("get_wake_status")),
    getResidentVoiceStatus: async () => JSON.parse(await invoke("get_resident_voice_status")),
    startWakeMonitor: async () => JSON.parse(await invoke("start_wake_monitor")),
    stopWakeMonitor: () => invoke("stop_wake_monitor"),
    toggleWakeMonitor: async () => JSON.parse(await invoke("toggle_wake_monitor")),
    getPersonalityList: async () => JSON.parse(await invoke("get_personality_list")),
    selectPersonality: async (profileId) => JSON.parse(await invoke("select_personality", { profileId })),
    getOperatorConfig: async () => JSON.parse(await invoke("get_operator_config")),
    writeOperatorConfig: async (fields) => JSON.parse(await invoke("write_operator_config", { fields })),
    submitText: async (text) => JSON.parse(await invoke("submit_text", { text })),
  };
}
