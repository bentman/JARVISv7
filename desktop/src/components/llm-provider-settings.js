const EDITABLE_KINDS = ["ollama", "openai_compatible", "openai", "anthropic"];

function element(tagName, text = "") {
  const value = document.createElement(tagName);
  value.textContent = text;
  return value;
}

function labeledControl(labelText, control) {
  const row = document.createElement("div");
  const label = element("label", labelText);
  label.appendChild(control);
  row.appendChild(label);
  return row;
}

function option(value, label, selected = false) {
  const item = document.createElement("option");
  item.value = value;
  item.textContent = label;
  item.selected = selected;
  return item;
}

function profileOption(profile, selectedId) {
  return option(profile.profile_id, `${profile.name} · ${profile.kind}`, profile.profile_id === selectedId);
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
  const heading = element("h3", "Model Providers");
  const summary = element(
    "p",
    "Choose the primary model provider, an optional local fallback, and an authorized cloud escalation target.",
  );
  const status = element("p");
  const selectionGroup = document.createElement("div");
  const primary = document.createElement("select");
  const fallback = document.createElement("select");
  const escalation = document.createElement("input");
  const cloud = document.createElement("select");
  const warning = element("p");
  const saveSelection = element("button", "Save provider selection");

  section.className = "settings-subsection model-provider-settings";
  escalation.type = "checkbox";
  escalation.checked = Boolean(selection.cloud_escalation_enabled);
  saveSelection.type = "button";
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

  selectionGroup.append(
    labeledControl("Primary provider", primary),
    labeledControl("Local fallback", fallback),
    labeledControl("Allow cloud escalation", escalation),
    labeledControl("Cloud provider", cloud),
    warning,
    saveSelection,
  );

  saveSelection.addEventListener("click", async () => {
    status.textContent = "Saving provider selection…";
    try {
      await handlers.updateLlmSelection(
        providerSelectionPayload(primary.value, fallback.value, escalation.checked, cloud.value),
      );
      status.textContent = "Provider selection saved. Restart required.";
      callbacks.onRestartRequired?.();
    } catch (error) {
      status.textContent = `Provider selection failed: ${error.message || error}`;
    }
  });

  const profileGroup = document.createElement("div");
  const profileHeading = element("h4", "Profiles");
  const profileSelect = document.createElement("select");
  const newProfile = element("button", "New profile");
  const name = document.createElement("input");
  const kind = document.createElement("select");
  const endpoint = document.createElement("input");
  const model = document.createElement("input");
  const modelList = document.createElement("datalist");
  const context = document.createElement("input");
  const timeout = document.createElement("input");
  const credential = document.createElement("input");
  const removeCredential = document.createElement("input");
  const save = element("button", "Save profile");
  const test = element("button", "Test connection");
  const remove = element("button", "Delete profile");
  const rotate = element("button", "Rotate credential-store key");
  const profileStatus = element("p");
  const controls = { name, kind, endpoint, model, context, timeout, credential, removeCredential, save, test, delete: remove };
  let editingProfile = selectedProfile(profiles, selection.primary_profile_id) || profiles[0] || null;

  fillProfileSelect(profileSelect, profiles, editingProfile?.profile_id);
  const managedOption = option("managed_llama_cpp", "managed llama.cpp");
  managedOption.disabled = true;
  kind.appendChild(managedOption);
  for (const value of EDITABLE_KINDS) kind.appendChild(option(value, value.replaceAll("_", " ")));
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
  for (const button of [newProfile, save, test, remove, rotate]) button.type = "button";
  setProfileFields(editingProfile, controls);

  profileSelect.addEventListener("change", () => {
    editingProfile = selectedProfile(profiles, profileSelect.value);
    setProfileFields(editingProfile, controls);
    profileStatus.textContent = "";
  });
  newProfile.addEventListener("click", () => {
    editingProfile = null;
    profileSelect.value = "";
    setProfileFields(null, controls);
    name.focus();
  });
  kind.addEventListener("change", () => updateEndpointState(controls));

  save.addEventListener("click", async () => {
    profileStatus.textContent = editingProfile ? "Saving profile…" : "Creating profile…";
    try {
      const wasSelected =
        editingProfile &&
        [selection.primary_profile_id, selection.local_fallback_profile_id, selection.cloud_profile_id].includes(
          editingProfile.profile_id,
        );
      if (editingProfile) {
        await handlers.updateLlmProfile(editingProfile.profile_id, profilePayload(controls));
      } else {
        await handlers.createLlmProfile(profilePayload(controls));
      }
      if (wasSelected) callbacks.onRestartRequired?.();
      await callbacks.reload?.();
    } catch (error) {
      profileStatus.textContent = `Profile save failed: ${error.message || error}`;
    }
  });

  test.addEventListener("click", async () => {
    if (!editingProfile) return;
    profileStatus.textContent = "Testing connection…";
    try {
      const result = await handlers.testLlmProfile(editingProfile.profile_id);
      modelList.replaceChildren(
        ...(result.models || []).map((item) => option(item.id, item.display_name || item.id)),
      );
      profileStatus.textContent = `${result.status}: ${result.reason}`;
    } catch (error) {
      profileStatus.textContent = `Connection test failed: ${error.message || error}`;
    }
  });

  remove.addEventListener("click", async () => {
    if (!editingProfile) return;
    profileStatus.textContent = "Deleting profile…";
    try {
      await handlers.deleteLlmProfile(editingProfile.profile_id);
      await callbacks.reload?.();
    } catch (error) {
      profileStatus.textContent = `Profile delete failed: ${error.message || error}`;
    }
  });

  rotate.addEventListener("click", async () => {
    profileStatus.textContent = "Rotating credential-store key…";
    try {
      await handlers.rotateSecretStoreKey();
      profileStatus.textContent = "Credential-store key rotated.";
    } catch (error) {
      profileStatus.textContent = `Key rotation failed: ${error.message || error}`;
    }
  });

  profileGroup.append(
    profileHeading,
    labeledControl("Profile", profileSelect),
    newProfile,
    labeledControl("Display name", name),
    labeledControl("Provider kind", kind),
    labeledControl("Endpoint", endpoint),
    labeledControl("Model ID", model),
    modelList,
    labeledControl("Context window", context),
    labeledControl("Timeout seconds", timeout),
    labeledControl("Credential", credential),
    labeledControl("Remove stored credential", removeCredential),
    save,
    test,
    remove,
    rotate,
    profileStatus,
  );
  section.append(heading, summary, selectionGroup, profileGroup, status);
  return section;
}
