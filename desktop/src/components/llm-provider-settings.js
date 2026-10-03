import { createRenderStateKeeper } from "./render-state.js";
import { confirmDestructive } from "./ui/confirm.js";
import { button, buttonRow, field, option } from "./ui/dom.js";
import { errorMessage, humanize, statusText } from "./ui/format.js";
import { renderPanelHeader } from "./ui/panel.js";

export const PROVIDER_TYPES = {
  unsloth: {
    label: "Unsloth (Local)",
    kind: "openai_compatible",
    endpoint: "http://127.0.0.1:4444/v1",
    context_window: 8192,
    timeout_seconds: 60,
    model: "default",
    fixedEndpoint: false,
    defaultName: "Unsloth Local",
  },
  llama_cpp: {
    label: "llama.cpp (Local)",
    kind: "openai_compatible",
    endpoint: "http://127.0.0.1:8080/v1",
    context_window: 8192,
    timeout_seconds: 60,
    model: "default",
    fixedEndpoint: false,
    defaultName: "llama.cpp Local",
  },
  ollama: {
    label: "Ollama (Local)",
    kind: "ollama",
    endpoint: "http://127.0.0.1:11434",
    context_window: 8192,
    timeout_seconds: 60,
    model: "llama3.2",
    fixedEndpoint: false,
    defaultName: "Ollama Local",
  },
  vllm: {
    label: "vLLM (Local)",
    kind: "openai_compatible",
    endpoint: "http://127.0.0.1:8000/v1",
    context_window: 8192,
    timeout_seconds: 60,
    model: "default",
    fixedEndpoint: false,
    defaultName: "vLLM Local",
  },
  openai_compatible: {
    label: "Custom OpenAI-compatible",
    kind: "openai_compatible",
    endpoint: "http://127.0.0.1:8080/v1",
    context_window: 8192,
    timeout_seconds: 60,
    model: "custom",
    fixedEndpoint: false,
    defaultName: "Custom OpenAI-compatible",
  },
  openai: {
    label: "OpenAI (Cloud)",
    kind: "openai",
    endpoint: "https://api.openai.com/v1",
    context_window: 128000,
    timeout_seconds: 60,
    model: "gpt-4o-mini",
    fixedEndpoint: true,
    defaultName: "OpenAI Cloud",
  },
  anthropic: {
    label: "Anthropic (Cloud)",
    kind: "anthropic",
    endpoint: "https://api.anthropic.com/v1",
    context_window: 200000,
    timeout_seconds: 60,
    model: "claude-sonnet-5-5",
    fixedEndpoint: true,
    defaultName: "Anthropic Cloud",
  },
};

const KNOWN_DEFAULT_NAMES = new Set([
  ...Object.values(PROVIDER_TYPES).map((p) => p.defaultName),
  ...Object.values(PROVIDER_TYPES).map((p) => p.label),
  "",
]);

const KIND_LABELS = {
  managed_llama_cpp: "Managed llama.cpp",
  ollama: "Ollama",
  openai_compatible: "OpenAI-compatible",
  openai: "OpenAI",
  anthropic: "Anthropic",
};

let pendingProfileFeedback = null;

export function profileToProviderType(profile) {
  if (!profile) return "llama_cpp";
  if (profile.kind === "managed_llama_cpp") return "llama_cpp";
  if (profile.kind === "ollama") return "ollama";
  if (profile.kind === "openai") return "openai";
  if (profile.kind === "anthropic") return "anthropic";
  if (profile.kind === "openai_compatible") {
    const ep = String(profile.endpoint || "");
    if (ep.includes(":4444")) return "unsloth";
    if (ep.includes(":8080")) return "llama_cpp";
    if (ep.includes(":8000")) return "vllm";
    return "openai_compatible";
  }
  return "openai_compatible";
}

function element(tagName, text = "", className = "") {
  const value = document.createElement(tagName);
  value.textContent = text;
  if (className) value.className = className;
  return value;
}

function setStatus(node, text, kind = "notice") {
  node.textContent = text;
  node.className = kind === "error" ? "panel-error" : "panel-notice";
}

function profileActiveStatus(profile, selection) {
  if (!profile) return null;
  if (profile.profile_id === selection?.primary_profile_id) return "Primary provider";
  if (profile.profile_id === selection?.local_fallback_profile_id) return "Local fallback";
  if (profile.profile_id === selection?.cloud_profile_id) return "Cloud provider";
  return null;
}

function profileOption(profile, selectedId) {
  const typeKey = profileToProviderType(profile);
  const typeLabel = PROVIDER_TYPES[typeKey]?.label || humanize(profile.kind, KIND_LABELS);
  return option(profile.profile_id, `${profile.name} · ${typeLabel}`, profile.profile_id === selectedId);
}

function fillProfileSelect(select, profiles, selectedId, emptyLabel = null) {
  select.replaceChildren();
  if (emptyLabel !== null) select.appendChild(option("", emptyLabel, !selectedId));
  for (const profile of profiles) select.appendChild(profileOption(profile, selectedId));
}

function selectedProfile(profiles, profileId) {
  return profiles.find((profile) => profile.profile_id === profileId) || null;
}

function localProfiles(profiles) {
  return profiles.filter(
    (profile) =>
      ["managed_llama_cpp", "ollama", "openai_compatible"].includes(profile.kind) &&
      !profile.cloud_eligible,
  );
}

function cloudProfiles(profiles) {
  return profiles.filter((profile) => profile.cloud_eligible);
}

function profilePayload(controls) {
  const selectedType = PROVIDER_TYPES[controls.type.value] || PROVIDER_TYPES.openai_compatible;
  return {
    name: controls.name.value.trim(),
    kind: selectedType.kind,
    endpoint: selectedType.fixedEndpoint ? selectedType.endpoint : controls.endpoint.value.trim() || null,
    model: controls.model.value.trim() || null,
    context_window: Number(controls.context.value) || selectedType.context_window,
    timeout_seconds: Number(controls.timeout.value) || selectedType.timeout_seconds,
    api_key: controls.credential.value.trim() || null,
    clear_api_key: controls.removeCredential.checked,
  };
}

export function providerSelectionPayload(primaryId, fallbackId, escalationEnabled, cloudId) {
  return {
    primary_profile_id: primaryId,
    local_fallback_profile_id: fallbackId || null,
    cloud_escalation_enabled: Boolean(escalationEnabled),
    cloud_profile_id: cloudId || null,
  };
}

export function defaultEditingProfile(profiles, selection, preferredProfileId = null) {
  const available = Array.isArray(profiles) ? profiles : [];
  return (
    selectedProfile(available, preferredProfileId) ||
    available.find((profile) => !profile.builtin) ||
    selectedProfile(available, selection?.primary_profile_id) ||
    available[0] ||
    null
  );
}

export function builtinProfileNotice(profile) {
  return profile?.builtin
    ? "This built-in profile is managed by the backend and cannot be edited. Use 'New profile' or 'Duplicate' to create an editable one."
    : "";
}

export function providerRestartDisabled(scopes) {
  return [...(scopes || [])].includes("provider");
}

export function providerChoiceGroups(profiles) {
  return {
    local: localProfiles(profiles).map((profile) => profile.profile_id),
    cloud: cloudProfiles(profiles).map((profile) => profile.profile_id),
  };
}

function updateEndpointState(controls, builtin = false) {
  const selectedType = PROVIDER_TYPES[controls.type.value] || PROVIDER_TYPES.openai_compatible;
  const isFixed = selectedType.fixedEndpoint;
  controls.endpoint.disabled = builtin || isFixed;
  controls.endpoint.placeholder = isFixed
    ? "Provider endpoint is fixed"
    : selectedType.endpoint;
  if (!builtin && isFixed) {
    controls.endpoint.value = selectedType.endpoint;
  }
}

function setProfileFields(profile, controls, selection = null) {
  const editable = Boolean(profile && !profile.builtin);
  const typeKey = profileToProviderType(profile);
  const typePreset = PROVIDER_TYPES[typeKey] || PROVIDER_TYPES.llama_cpp;

  controls.type.value = typeKey;
  controls.name.value = profile?.name || typePreset.defaultName;
  controls.endpoint.value = profile?.endpoint || (profile ? "" : typePreset.endpoint);
  controls.model.value = profile?.model || (profile ? "" : typePreset.model);
  controls.context.value = String(profile?.context_window || typePreset.context_window);
  controls.timeout.value = String(profile?.timeout_seconds || typePreset.timeout_seconds);
  controls.credential.value = "";
  controls.credential.placeholder = profile?.has_secret ? "Stored; enter replacement" : "Optional bearer or API key";
  controls.removeCredential.checked = false;
  controls.removeCredential.disabled = !editable || !profile?.has_secret;

  for (const control of [
    controls.name,
    controls.type,
    controls.endpoint,
    controls.model,
    controls.context,
    controls.timeout,
    controls.credential,
  ]) {
    control.disabled = !editable && Boolean(profile);
  }

  const activeRole = profileActiveStatus(profile, selection);
  if (controls.activeBadge) {
    if (activeRole) {
      controls.activeBadge.textContent = `Active: ${activeRole}`;
      controls.activeBadge.className = "profile-status-badge active-role-badge";
      controls.activeBadge.hidden = false;
    } else if (profile?.builtin) {
      controls.activeBadge.textContent = "Built-in";
      controls.activeBadge.className = "profile-status-badge builtin-badge";
      controls.activeBadge.hidden = false;
    } else {
      controls.activeBadge.textContent = "";
      controls.activeBadge.hidden = true;
    }
  }

  if (controls.notice) {
    controls.notice.textContent = builtinProfileNotice(profile);
    controls.notice.hidden = !profile?.builtin;
  }

  controls.save.textContent = profile ? "Save profile" : "Create profile";
  controls.save.disabled = Boolean(profile?.builtin);

  const isProtectedActive = Boolean(activeRole);
  controls.delete.disabled = !profile || profile.builtin || isProtectedActive;
  if (isProtectedActive) {
    controls.delete.title = `Cannot delete: currently active as ${activeRole}. Change provider selection first.`;
  } else if (profile?.builtin) {
    controls.delete.title = "Built-in profiles cannot be deleted.";
  } else {
    controls.delete.title = "Delete this profile";
  }

  controls.test.disabled = false;
  updateEndpointState(controls, profile?.builtin === true);
}

export function createLlmProviderSettings(payload, handlers, callbacks = {}) {
  const profiles = Array.isArray(payload?.profiles) ? payload.profiles : [];
  const selection = payload?.selection || {};
  const section = document.createElement("section");
  section.className = "model-provider-settings";

  const heading = element("h3", "Model providers");
  const summary = element(
    "p",
    "Model providers · Configure active routing, fallback, and cloud escalation across profiles.",
    "panel-help",
  );
  const status = element("p");
  status.setAttribute("aria-live", "polite");

  const selectionGroup = document.createElement("div");
  selectionGroup.className = "model-provider-selection-column";
  const selectionHeading = element("h4", "Provider Routing & Escalation");
  const selectionSubtext = element(
    "p",
    "Assign the active primary model provider, optional local fallback, and authorized cloud escalation target.",
    "panel-help",
  );

  const primary = document.createElement("select");
  const fallback = document.createElement("select");
  const escalation = document.createElement("input");
  const cloud = document.createElement("select");
  const warning = element("p", "", "panel-help");
  const saveSelection = button("Save routing selection", { variant: "primary", focusKey: "provider:save-selection" });

  escalation.type = "checkbox";
  escalation.checked = Boolean(selection.cloud_escalation_enabled);
  primary.dataset.draftKey = "provider-selection:primary";
  fallback.dataset.draftKey = "provider-selection:fallback";
  escalation.dataset.draftKey = "provider-selection:escalation";
  cloud.dataset.draftKey = "provider-selection:cloud";
  fillProfileSelect(primary, profiles, selection.primary_profile_id);
  fillProfileSelect(fallback, localProfiles(profiles), selection.local_fallback_profile_id, "No local fallback");
  fillProfileSelect(cloud, cloudProfiles(profiles), selection.cloud_profile_id, "No cloud profile");
  cloud.disabled = !escalation.checked;

  const renderWarning = () => {
    const profile = selectedProfile(profiles, primary.value);
    warning.textContent = profile?.cloud_eligible
      ? "Remote provider selected as primary. Normal turns may send bounded conversation and memory context to it."
      : escalation.checked
        ? "Eligible local failures and explicit cloud requests may use the selected cloud profile."
        : "Cloud escalation is disabled.";
  };
  primary.addEventListener("change", renderWarning);
  escalation.addEventListener("change", () => {
    cloud.disabled = !escalation.checked;
    renderWarning();
  });
  renderWarning();

  const escalationLabel = document.createElement("label");
  escalationLabel.className = "panel-choice";
  escalationLabel.append(escalation, element("span", "Allow cloud escalation"));

  selectionGroup.append(
    selectionHeading,
    selectionSubtext,
    field("Primary provider", primary),
    field("Local fallback", fallback),
    escalationLabel,
    field("Cloud provider", cloud),
    warning,
    buttonRow(saveSelection),
  );

  saveSelection.addEventListener("click", async () => {
    setStatus(status, "Saving provider selection…");
    try {
      await handlers.updateLlmSelection(
        providerSelectionPayload(primary.value, fallback.value, escalation.checked, cloud.value),
      );
      setStatus(status, "Provider selection saved. It applies after a backend restart.");
      callbacks.onRestartRequired?.();
    } catch (error) {
      setStatus(status, `Provider selection failed: ${errorMessage(error)}`, "error");
    }
  });

  const profileGroup = document.createElement("div");
  profileGroup.className = "model-provider-profile-column";
  const profileHeading = element("h4", "Provider Profiles");
  const profileSubtext = element(
    "p",
    "Configure local model servers (Unsloth, llama.cpp, Ollama, vLLM) and cloud API endpoints.",
    "panel-help",
  );
  const profileSelect = document.createElement("select");
  const newProfile = button("New profile", { focusKey: "provider:new" });
  const duplicate = button("Duplicate", { focusKey: "provider:duplicate" });
  duplicate.title = "Clone currently selected profile into an editable new profile";

  const activeBadge = document.createElement("span");
  activeBadge.className = "profile-status-badge";
  activeBadge.hidden = true;

  const name = document.createElement("input");
  const typeSelect = document.createElement("select");
  const sortedTypes = Object.entries(PROVIDER_TYPES).sort((a, b) =>
    a[1].label.localeCompare(b[1].label),
  );
  for (const [key, preset] of sortedTypes) {
    typeSelect.appendChild(option(key, preset.label));
  }

  const endpoint = document.createElement("input");
  const model = document.createElement("input");
  const modelSelect = document.createElement("select");
  modelSelect.className = "model-select-dropdown hidden";
  modelSelect.id = "llm-provider-model-select";
  modelSelect.setAttribute("aria-label", "Discovered Model ID");
  const modelList = document.createElement("datalist");
  const context = document.createElement("input");
  const timeout = document.createElement("input");
  const credential = document.createElement("input");
  const removeCredential = document.createElement("input");
  const save = button("Save profile", { variant: "primary", focusKey: "provider:save" });
  const test = button("Test connection", { focusKey: "provider:test" });
  const remove = button("Delete profile", { variant: "danger", focusKey: "provider:delete" });
  const rotate = button("Rotate credential-store key", { variant: "danger", focusKey: "provider:rotate" });
  const profileStatus = element("p");
  profileStatus.setAttribute("aria-live", "polite");
  const profileNotice = element("p");
  profileNotice.className = "model-provider-notice";

  const controls = {
    name,
    type: typeSelect,
    kind: typeSelect,
    endpoint,
    model,
    context,
    timeout,
    credential,
    removeCredential,
    save,
    test,
    delete: remove,
    notice: profileNotice,
    activeBadge,
  };

  let editingProfile = defaultEditingProfile(profiles, selection, callbacks.preferredProfileId);
  fillProfileSelect(profileSelect, profiles, editingProfile?.profile_id);
  profileSelect.value = editingProfile?.profile_id || "";

  modelList.id = "llm-provider-models";
  model.setAttribute("list", modelList.id);
  context.type = "number";
  context.min = "512";
  context.max = "2000000";
  timeout.type = "number";
  timeout.min = "1";
  timeout.max = "600";
  credential.type = "password";
  removeCredential.type = "checkbox";

  const populateModelSelect = (models) => {
    if (Array.isArray(models) && models.length > 0) {
      modelSelect.replaceChildren(
        option("", `Select from ${models.length} discovered model${models.length === 1 ? "" : "s"}…`),
        ...models.map((item) => {
          const ctxText = item.context_window ? ` (${item.context_window} ctx)` : "";
          const opt = option(item.id, `${item.display_name || item.id}${ctxText}`);
          if (item.context_window) opt.dataset.contextWindow = String(item.context_window);
          return opt;
        }),
        option("__custom__", "Custom / manual Model ID…"),
      );
      modelSelect.classList.remove("hidden");
      if (models.some((item) => item.id === model.value)) {
        modelSelect.value = model.value;
      }
    } else {
      modelSelect.replaceChildren();
      modelSelect.classList.add("hidden");
    }
  };

  modelSelect.addEventListener("change", () => {
    if (modelSelect.value && modelSelect.value !== "__custom__") {
      model.value = modelSelect.value;
      const selectedOpt = modelSelect.options[modelSelect.selectedIndex];
      if (selectedOpt?.dataset?.contextWindow) {
        context.value = selectedOpt.dataset.contextWindow;
      }
      model.dispatchEvent(new Event("input", { bubbles: true }));
    } else if (modelSelect.value === "__custom__") {
      model.focus();
    }
  });

  model.addEventListener("input", () => {
    if (modelSelect.options?.length) {
      modelSelect.value = [...modelSelect.options].some((opt) => opt.value === model.value) ? model.value : "";
    }
  });

  const keyFields = () => {
    const scope = editingProfile?.profile_id || "new";
    for (const [key, control] of Object.entries({ name, type: typeSelect, endpoint, model, context, timeout })) {
      control.dataset.draftKey = `provider:${scope}:${key}`;
    }
  };
  keyFields();
  setProfileFields(editingProfile, controls, selection);

  if (pendingProfileFeedback) {
    setStatus(profileStatus, pendingProfileFeedback.text, pendingProfileFeedback.kind);
    pendingProfileFeedback = null;
  }

  profileSelect.addEventListener("change", () => {
    editingProfile = selectedProfile(profiles, profileSelect.value);
    callbacks.onEditingProfile?.(editingProfile?.profile_id || null);
    keyFields();
    setProfileFields(editingProfile, controls, selection);
    modelSelect.replaceChildren();
    modelSelect.classList.add("hidden");
    profileStatus.textContent = "";
  });

  newProfile.addEventListener("click", () => {
    editingProfile = null;
    callbacks.onEditingProfile?.(null);
    profileSelect.value = "";
    keyFields();
    setProfileFields(null, controls, selection);

    modelSelect.replaceChildren();
    modelSelect.classList.add("hidden");
    setStatus(profileStatus, 'New profile draft. Edit settings and click "Create profile".');
    typeSelect.focus();
  });

  duplicate.addEventListener("click", () => {
    const sourceProfile = editingProfile || profiles[0];
    if (!sourceProfile) return;
    editingProfile = null;
    callbacks.onEditingProfile?.(null);
    profileSelect.value = "";
    keyFields();

    setProfileFields(null, controls, selection);
    controls.name.value = `${sourceProfile.name} (Copy)`;
    const typeKey = profileToProviderType(sourceProfile);
    controls.type.value = typeKey;
    updateEndpointState(controls);
    if (sourceProfile.endpoint) controls.endpoint.value = sourceProfile.endpoint;
    if (sourceProfile.model) controls.model.value = sourceProfile.model;
    controls.context.value = String(sourceProfile.context_window || 8192);
    controls.timeout.value = String(sourceProfile.timeout_seconds || 60);

    modelSelect.replaceChildren();
    modelSelect.classList.add("hidden");
    setStatus(profileStatus, `Cloned from "${sourceProfile.name}". Adjust parameters and click "Create profile".`);
    controls.name.focus();
  });

  typeSelect.addEventListener("change", () => {
    const preset = PROVIDER_TYPES[typeSelect.value] || PROVIDER_TYPES.llama_cpp;
    updateEndpointState(controls);
    if (!controls.endpoint.disabled) {
      controls.endpoint.value = preset.endpoint;
    }
    controls.model.value = preset.model;
    controls.context.value = String(preset.context_window);
    controls.timeout.value = String(preset.timeout_seconds);
    if (!editingProfile || KNOWN_DEFAULT_NAMES.has(controls.name.value.trim())) {
      controls.name.value = preset.defaultName || preset.label;
    }
    modelSelect.replaceChildren();
    modelSelect.classList.add("hidden");
  });

  save.addEventListener("click", async () => {
    setStatus(profileStatus, editingProfile ? "Saving profile…" : "Creating profile…");
    try {
      const wasSelected =
        editingProfile &&
        [selection.primary_profile_id, selection.local_fallback_profile_id, selection.cloud_profile_id].includes(
          editingProfile.profile_id,
        );
      const isNew = !editingProfile;
      const profileName = controls.name.value.trim() || "Profile";
      const saved = editingProfile
        ? await handlers.updateLlmProfile(editingProfile.profile_id, profilePayload(controls))
        : await handlers.createLlmProfile(profilePayload(controls));

      pendingProfileFeedback = {
        text: isNew
          ? `Profile "${profileName}" created successfully.`
          : `Profile "${profileName}" saved successfully.${wasSelected ? " Restart backend to apply to active turns." : ""}`,
        kind: "notice",
      };

      if (wasSelected) callbacks.onRestartRequired?.();
      await callbacks.reload?.({ selectProfileId: saved?.profile_id || editingProfile?.profile_id || null });
    } catch (error) {
      setStatus(profileStatus, `Profile save failed: ${errorMessage(error)}`, "error");
    }
  });

  test.addEventListener("click", async () => {
    setStatus(profileStatus, "Testing connection…");
    try {
      const payload = editingProfile?.builtin ? null : profilePayload(controls);
      const profileId = editingProfile?.profile_id || "new";
      const result = await handlers.testLlmProfile(profileId, payload);
      const models = result.models || [];
      modelList.replaceChildren(
        ...models.map((item) => option(item.id, item.display_name || item.id)),
      );
      populateModelSelect(models);
      const reachable = ["ready", "configured"].includes(result.status);
      const modelCountText = models.length > 0 ? ` (${models.length} model${models.length === 1 ? "" : "s"} discovered)` : "";
      setStatus(profileStatus, `${statusText(result.status)}: ${result.reason}${modelCountText}`, reachable ? "notice" : "error");
    } catch (error) {
      setStatus(profileStatus, `Connection test failed: ${errorMessage(error)}`, "error");
    }
  });

  const confirm = callbacks.confirm || confirmDestructive;
  remove.addEventListener("click", async () => {
    if (!editingProfile) return;
    if (!(await confirm(`Delete the provider profile "${editingProfile.name}"?`))) return;
    setStatus(profileStatus, "Deleting profile…");
    try {
      await handlers.deleteLlmProfile(editingProfile.profile_id);
      pendingProfileFeedback = {
        text: `Profile "${editingProfile.name}" deleted.`,
        kind: "notice",
      };
      await callbacks.reload?.({ selectProfileId: null });
    } catch (error) {
      setStatus(profileStatus, `Profile delete failed: ${errorMessage(error)}`, "error");
    }
  });

  rotate.addEventListener("click", async () => {
    if (!(await confirm("Rotate the credential-store key? Stored credentials are re-encrypted with a new key."))) return;
    setStatus(profileStatus, "Rotating credential-store key…");
    try {
      await handlers.rotateSecretStoreKey();
      setStatus(profileStatus, "Credential-store key rotated.");
    } catch (error) {
      setStatus(profileStatus, `Key rotation failed: ${errorMessage(error)}`, "error");
    }
  });

  const removeCredentialLabel = document.createElement("label");
  removeCredentialLabel.className = "panel-choice";
  removeCredentialLabel.append(removeCredential, element("span", "Remove stored credential"));
  const modelWrapper = document.createElement("div");
  modelWrapper.append(modelSelect, model);
  const modelField = field("Model ID", modelWrapper);

  const profileToolbar = document.createElement("div");
  profileToolbar.className = "model-provider-toolbar";
  profileToolbar.append(newProfile, duplicate);

  profileGroup.append(
    profileHeading,
    profileSubtext,
    field("Profile", profileSelect),
    profileToolbar,
    activeBadge,
    field("Provider type", typeSelect),
    field("Display name", name),
    field("Endpoint", endpoint),
    modelField,
    modelList,
    field("Context window", context),
    field("Timeout seconds", timeout),
    field("Credential", credential),
    removeCredentialLabel,
    buttonRow(save, test, remove),
    profileNotice,
    profileStatus,
    buttonRow(rotate),
  );

  const layout = document.createElement("div");
  layout.className = "model-provider-layout";
  layout.append(selectionGroup, profileGroup);
  section.append(heading, summary, layout, status);

  if (providerRestartDisabled(callbacks.restartScopes)) {
    for (const control of [
      saveSelection, save, remove, rotate, newProfile, duplicate,
      primary, fallback, escalation, cloud,
      name, typeSelect, endpoint, model, context, timeout, credential, removeCredential,
    ]) {
      control.disabled = true;
    }
  }
  return section;
}

let activeProviderContainer = null;
let providerKeeper = null;
let providerGeneration = 0;
let providerHandlers = null;
let providerOptions = {};
let preferredProfileId = null;

function providerUnavailable(containerEl, message) {
  containerEl.replaceChildren(renderPanelHeader("Provider Model Profiles"), element("p", message, "panel-error"));
}

function renderProviderPanel(containerEl, payload) {
  const scopes = providerOptions.restartRequiredScopes?.() || [];
  const restartState = element("p", "Saved provider changes apply after a backend restart.", "panel-notice");
  const restartButton = button("Restart backend", { variant: "primary", focusKey: "provider:restart" });
  restartState.hidden = scopes.length === 0;
  restartButton.hidden = scopes.length === 0;
  restartButton.addEventListener("click", async () => {
    setStatus(restartState, "Restarting the backend…");
    try {
      await providerOptions.restartBackend?.();
      providerOptions.clearRestartRequired?.();
      await loadProviderSettings(containerEl);
    } catch (error) {
      setStatus(restartState, errorMessage(error, "Restart failed."), "error");
    }
  });

  const settings = createLlmProviderSettings(payload, providerHandlers, {
    preferredProfileId,
    restartScopes: scopes,
    onRestartRequired: () => {
      providerOptions.markRestartRequired?.("provider");
      loadProviderSettings(containerEl);
    },
    reload: (result = {}) => {
      if ("selectProfileId" in result) preferredProfileId = result.selectProfileId;
      return loadProviderSettings(containerEl);
    },
    onEditingProfile: (profileId) => {
      preferredProfileId = profileId;
    },
  });

  const children = [renderPanelHeader("Provider Model Profiles"), restartState, buttonRow(restartButton), settings];
  if (providerKeeper?.container === containerEl) providerKeeper.render(...children);
  else containerEl.replaceChildren(...children);
}

async function loadProviderSettings(containerEl) {
  const request = ++providerGeneration;
  if (!providerHandlers?.getLlmConfig) {
    providerUnavailable(containerEl, "Providers are unavailable.");
    return;
  }
  let payload;
  try {
    payload = await providerHandlers.getLlmConfig();
  } catch (error) {
    if (request !== providerGeneration || activeProviderContainer !== containerEl) return;
    providerUnavailable(containerEl, "Providers are unavailable.");
    return;
  }
  if (request !== providerGeneration || activeProviderContainer !== containerEl) return;
  renderProviderPanel(containerEl, payload);
}

export async function openProviderSettings(containerEl, options = {}) {
  activeProviderContainer = containerEl;
  providerHandlers = options.handlers || providerHandlers;
  providerOptions = { ...providerOptions, ...options };
  if (providerKeeper?.container !== containerEl) {
    providerKeeper = Object.assign(createRenderStateKeeper(containerEl), { container: containerEl });
  }
  containerEl.hidden = false;
  if (!containerEl.childNodes?.length) containerEl.replaceChildren(renderPanelHeader("Provider Model Profiles"), element("p", "Loading providers…", "panel-help"));
  await loadProviderSettings(containerEl);
  if (activeProviderContainer !== containerEl) return;
  providerKeeper.release();
  containerEl.querySelector("h2")?.focus();
}

export function closeProviderSettings() {
  if (!activeProviderContainer) return;
  providerGeneration += 1;
  if (providerKeeper?.container === activeProviderContainer) providerKeeper.retain();
  activeProviderContainer.hidden = true;
  activeProviderContainer.replaceChildren();
  activeProviderContainer = null;
  preferredProfileId = null;
  providerOptions.onClose?.();
}

export function providerSettingsOpen() {
  return Boolean(activeProviderContainer);
}
