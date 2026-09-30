import { createRenderStateKeeper } from "./render-state.js";
import { confirmDestructive } from "./ui/confirm.js";
import { button, buttonRow, field, option } from "./ui/dom.js";
import { errorMessage, humanize, statusText } from "./ui/format.js";
import { renderPanelHeader } from "./ui/panel.js";

const EDITABLE_KINDS = ["ollama", "openai_compatible", "openai", "anthropic"];

const KIND_LABELS = {
  managed_llama_cpp: "Managed llama.cpp",
  ollama: "Ollama",
  openai_compatible: "OpenAI-compatible",
  openai: "OpenAI",
  anthropic: "Anthropic",
};

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

function profileOption(profile, selectedId) {
  return option(profile.profile_id, `${profile.name} · ${humanize(profile.kind, KIND_LABELS)}`, profile.profile_id === selectedId);
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
  return {
    name: controls.name.value.trim(),
    kind: controls.kind.value,
    endpoint: controls.endpoint.value.trim() || null,
    model: controls.model.value.trim() || null,
    context_window: Number(controls.context.value),
    timeout_seconds: Number(controls.timeout.value),
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
    ? "This built-in profile is managed by the backend and cannot be edited. Use New profile to create an editable one."
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

function setProfileFields(profile, controls) {
  const editable = Boolean(profile && !profile.builtin);
  controls.name.value = profile?.name || "";
  controls.kind.value = profile?.kind === "managed_llama_cpp" ? "openai_compatible" : profile?.kind || "openai_compatible";
  controls.endpoint.value = profile?.endpoint || "";
  controls.model.value = profile?.model || "";
  controls.context.value = String(profile?.context_window || 8192);
  controls.timeout.value = String(profile?.timeout_seconds || 60);
  controls.credential.value = "";
  controls.credential.placeholder = profile?.has_secret ? "Stored; enter replacement" : "Optional bearer or API key";
  controls.removeCredential.checked = false;
  controls.removeCredential.disabled = !editable || !profile?.has_secret;
  for (const control of [
    controls.name,
    controls.kind,
    controls.endpoint,
    controls.model,
    controls.context,
    controls.timeout,
    controls.credential,
  ]) {
    control.disabled = !editable && Boolean(profile);
  }
  if (controls.notice) controls.notice.textContent = builtinProfileNotice(profile);
  controls.save.textContent = profile ? "Save profile" : "Create profile";
  controls.save.disabled = Boolean(profile?.builtin);
  controls.delete.disabled = !profile || profile.builtin;
  controls.test.disabled = !profile;
  updateEndpointState(controls, profile?.builtin === true);
}

function updateEndpointState(controls, builtin = false) {
  const fixedEndpoint = ["openai", "anthropic"].includes(controls.kind.value);
  controls.endpoint.disabled = builtin || fixedEndpoint;
  controls.endpoint.placeholder = fixedEndpoint
    ? "Provider endpoint is fixed"
    : controls.kind.value === "ollama"
      ? "http://127.0.0.1:11434"
      : "http://127.0.0.1:8080/v1";
}

export function createLlmProviderSettings(payload, handlers, callbacks = {}) {
  const profiles = Array.isArray(payload?.profiles) ? payload.profiles : [];
  const selection = payload?.selection || {};
  const section = document.createElement("section");
  const heading = element("h3", "Model providers");
  const summary = element(
    "p",
    "Choose the primary model provider, an optional local fallback, and an authorized cloud escalation target.",
    "panel-help",
  );
  const status = element("p");
  status.setAttribute("aria-live", "polite");
  const selectionGroup = document.createElement("div");
  const primary = document.createElement("select");
  const fallback = document.createElement("select");
  const escalation = document.createElement("input");
  const cloud = document.createElement("select");
  const warning = element("p", "", "panel-help");
  const saveSelection = button("Save provider selection", { variant: "primary", focusKey: "provider:save-selection" });

  section.className = "model-provider-settings";
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
  const profileHeading = element("h4", "Profiles");
  const profileSelect = document.createElement("select");
  const newProfile = button("New profile", { focusKey: "provider:new" });
  const name = document.createElement("input");
  const kind = document.createElement("select");
  const endpoint = document.createElement("input");
  const model = document.createElement("input");
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
  const controls = { name, kind, endpoint, model, context, timeout, credential, removeCredential, save, test, delete: remove, notice: profileNotice };
  let editingProfile = defaultEditingProfile(profiles, selection, callbacks.preferredProfileId);

  fillProfileSelect(profileSelect, profiles, editingProfile?.profile_id);
  profileSelect.value = editingProfile?.profile_id || "";
  const managedOption = option("managed_llama_cpp", "managed llama.cpp");
  managedOption.disabled = true;
  kind.appendChild(managedOption);
  for (const value of EDITABLE_KINDS) kind.appendChild(option(value, KIND_LABELS[value]));
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
  // Unsaved edits are keyed to the profile being edited, so a re-render keeps them and switching
  // profiles never carries one profile's edits into another.
  const keyFields = () => {
    const scope = editingProfile?.profile_id || "new";
    for (const [key, control] of Object.entries({ name, kind, endpoint, model, context, timeout })) {
      control.dataset.draftKey = `provider:${scope}:${key}`;
    }
  };
  keyFields();
  setProfileFields(editingProfile, controls);

  profileSelect.addEventListener("change", () => {
    editingProfile = selectedProfile(profiles, profileSelect.value);
    callbacks.onEditingProfile?.(editingProfile?.profile_id || null);
    keyFields();
    setProfileFields(editingProfile, controls);
    profileStatus.textContent = "";
  });
  newProfile.addEventListener("click", () => {
    editingProfile = null;
    callbacks.onEditingProfile?.(null);
    profileSelect.value = "";
    keyFields();
    setProfileFields(null, controls);
    name.focus();
  });
  kind.addEventListener("change", () => updateEndpointState(controls));

  save.addEventListener("click", async () => {
    setStatus(profileStatus, editingProfile ? "Saving profile…" : "Creating profile…");
    try {
      const wasSelected =
        editingProfile &&
        [selection.primary_profile_id, selection.local_fallback_profile_id, selection.cloud_profile_id].includes(
          editingProfile.profile_id,
        );
      const saved = editingProfile
        ? await handlers.updateLlmProfile(editingProfile.profile_id, profilePayload(controls))
        : await handlers.createLlmProfile(profilePayload(controls));
      if (wasSelected) callbacks.onRestartRequired?.();
      await callbacks.reload?.({ selectProfileId: saved?.profile_id || editingProfile?.profile_id || null });
    } catch (error) {
      setStatus(profileStatus, `Profile save failed: ${errorMessage(error)}`, "error");
    }
  });

  test.addEventListener("click", async () => {
    if (!editingProfile) return;
    setStatus(profileStatus, "Testing connection…");
    try {
      const result = await handlers.testLlmProfile(editingProfile.profile_id);
      modelList.replaceChildren(
        ...(result.models || []).map((item) => option(item.id, item.display_name || item.id)),
      );
      const reachable = ["ready", "configured"].includes(result.status);
      setStatus(profileStatus, `${statusText(result.status)}: ${result.reason}`, reachable ? "notice" : "error");
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
  profileGroup.append(
    profileHeading,
    field("Profile", profileSelect),
    buttonRow(newProfile),
    field("Display name", name),
    field("Provider kind", kind),
    field("Endpoint", endpoint),
    field("Model ID", model),
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
  section.append(heading, summary, selectionGroup, profileGroup, status);
  if (providerRestartDisabled(callbacks.restartScopes)) {
    // A pending provider restart freezes provider writes only. Browsing profiles and testing a
    // connection stay available because both are read-only.
    for (const control of [
      saveSelection, save, remove, rotate, newProfile,
      primary, fallback, escalation, cloud,
      name, kind, endpoint, model, context, timeout, credential, removeCredential,
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
  containerEl.replaceChildren(renderPanelHeader("Providers & Models"), element("p", message, "panel-error"));
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

  const children = [renderPanelHeader("Providers & Models"), restartState, buttonRow(restartButton), settings];
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
  if (!containerEl.childNodes?.length) containerEl.replaceChildren(renderPanelHeader("Providers & Models"), element("p", "Loading providers…", "panel-help"));
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
