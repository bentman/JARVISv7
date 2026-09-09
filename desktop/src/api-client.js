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

function memoryApiError(error) {
  const message = String(error?.message || error || "Backend operation failed.");
  let payload;
  try {
    payload = JSON.parse(message);
  } catch {
    payload = { status: null, body: null, message };
  }
  const detail = payload.body?.detail;
  const bodyMessage =
    (detail && typeof detail === "object" ? detail.message : null) ||
    (typeof detail === "string" ? detail : null) ||
    payload.body?.message;
  const wrapped = new Error(bodyMessage || payload.message || "Backend operation failed.");
  wrapped.status = payload.status ?? null;
  wrapped.body = payload.body ?? null;
  wrapped.detail = detail ?? null;
  return wrapped;
}

async function invokeMemory(invoke, command, args = {}) {
  try {
    return parseJson(await invoke(command, args));
  } catch (error) {
    throw memoryApiError(error);
  }
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
    getDesktopStatus: async () => parseJson(await invoke("get_desktop_status")),
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
    getLlmConfig: () => invokeMemory(invoke, "get_llm_config"),
    createLlmProfile: (profile) => invokeMemory(invoke, "create_llm_profile", { profile }),
    updateLlmProfile: (profileId, profile) =>
      invokeMemory(invoke, "update_llm_profile", { profileId, profile }),
    deleteLlmProfile: (profileId) => invokeMemory(invoke, "delete_llm_profile", { profileId }),
    testLlmProfile: (profileId) => invokeMemory(invoke, "test_llm_profile", { profileId }),
    updateLlmSelection: (selection) => invokeMemory(invoke, "update_llm_selection", { selection }),
    rotateSecretStoreKey: () => invokeMemory(invoke, "rotate_secret_store_key"),
    getMemoryPolicy: () => invokeMemory(invoke, "get_memory_policy"),
    getMemoryLayers: () => invokeMemory(invoke, "get_memory_layers"),
    getArtifactRetentionPolicy: () => invokeMemory(invoke, "get_artifact_retention_policy"),
    updateMemoryPolicy: (automaticCurationEnabled, expectedRevision) =>
      invokeMemory(invoke, "update_memory_policy", { automaticCurationEnabled, expectedRevision }),
    listMemories: ({ lifecycleState = null, kind = null, query = null, offset = 0, limit = 20 } = {}) =>
      invokeMemory(invoke, "list_memories", { lifecycleState, kind, query, offset, limit }),
    getMemoryDetail: (factId) => invokeMemory(invoke, "get_memory_detail", { factId }),
    confirmMemory: (factId, expectedRevision, reason = null) =>
      invokeMemory(invoke, "confirm_memory", { factId, expectedRevision, reason }),
    correctMemory: (factId, expectedRevision, replacementText, replacementValue = null, reason = null) =>
      invokeMemory(invoke, "correct_memory", {
        factId,
        expectedRevision,
        replacementText,
        replacementValue,
        reason,
      }),
    disputeMemory: (factId, expectedRevision, reason = null) =>
      invokeMemory(invoke, "dispute_memory", { factId, expectedRevision, reason }),
    forgetMemory: (factId, expectedRevision, reason = null) =>
      invokeMemory(invoke, "forget_memory", { factId, expectedRevision, reason }),
    getMemoryCurationStatus: () => invokeMemory(invoke, "get_memory_curation_status"),
    getActionCapabilities: () => invokeMemory(invoke, "get_action_capabilities"),
    getPendingActions: () => invokeMemory(invoke, "get_pending_actions"),
    getActionAudit: (limit = 20) => invokeMemory(invoke, "get_action_audit", { limit }),
    proposeAction: ({ capabilityId, actionArguments = {}, reason, proposedBy = "operator" } = {}) =>
      invokeMemory(invoke, "propose_action", {
        capabilityId,
        arguments: actionArguments,
        reason,
        proposedBy,
      }),
    getActionStatus: (proposalId) => invokeMemory(invoke, "get_action_status", { proposalId }),
    decideAction: (proposalId, outcome, reason = null) =>
      invokeMemory(invoke, "decide_action", { proposalId, outcome, reason }),
    cancelAction: (proposalId) => invokeMemory(invoke, "cancel_action", { proposalId }),
    getExtensions: () => invokeMemory(invoke, "get_extensions"),
    getExtensionErrors: () => invokeMemory(invoke, "get_extension_errors"),
    getExtensionDetail: (extensionId) => invokeMemory(invoke, "get_extension_detail", { extensionId }),
    getExtensionBody: (extensionId) => invokeMemory(invoke, "get_extension_body", { extensionId }),
    getExtensionDefinition: (extensionId) =>
      invokeMemory(invoke, "get_extension_definition", { extensionId }),
    setExtensionState: (extensionId, extensionState, expectedRevision = null, reason = null) =>
      invokeMemory(invoke, "set_extension_state", {
        extensionId,
        extensionState,
        expectedRevision,
        reason,
      }),
    getExtensionRuntime: (extensionId) => invokeMemory(invoke, "get_extension_runtime", { extensionId }),
    getExtensionRuns: () => invokeMemory(invoke, "get_extension_runs"),
    invokeExtension: (extensionId, capabilityId, actionArguments = {}) =>
      invokeMemory(invoke, "invoke_extension", { extensionId, capabilityId, actionArguments }),
    answerExtensionInput: (runId, requestId, answer) =>
      invokeMemory(invoke, "answer_extension_input", { runId, requestId, answer }),
    writeExtensionCredential: (extensionId, name, secret) =>
      invokeMemory(invoke, "write_extension_credential", { extensionId, name, secret }),
    getExtensionOauth: (extensionId) => invokeMemory(invoke, "get_extension_oauth", { extensionId }),
    startExtensionOauth: (extensionId) =>
      invokeMemory(invoke, "start_extension_oauth", { extensionId }),
    completeExtensionOauth: (extensionId, code, oauthState) =>
      invokeMemory(invoke, "complete_extension_oauth", { extensionId, code, oauthState }),
    forgetExtensionOauth: (extensionId) =>
      invokeMemory(invoke, "forget_extension_oauth", { extensionId }),
    submitText: async (text) => parseJson(await invoke("submit_text", { text })),
    cancelSearch: async (sessionId, turnId) => parseJson(await invoke("cancel_search", { sessionId, turnId })),
    openSearchSource: (url) => invoke("open_search_source", { url }),
    listAgents: () => invokeMemory(invoke, "list_agents"),
    getAgent: (profileId) => invokeMemory(invoke, "get_agent", { profileId }),
    invokeAgent: (profileId, prompt) =>
      invokeMemory(invoke, "invoke_agent", { profileId, prompt }),
    listAgentRuns: () => invokeMemory(invoke, "list_agent_runs"),
    cancelAgent: (profileId) => invokeMemory(invoke, "cancel_agent", { profileId }),
  };
}
