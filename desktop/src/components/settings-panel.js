let activeContainer = null;
let loadedFields = [];
let fieldControls = new Map();
let statusEl = null;
let dirtyEl = null;
let restartRequired = false;
let restartHandler = null;
let restartRequiredChangeHandler = null;
let getConfigHandler = null;
let writeConfigHandler = null;

function fieldLabel(field) {
  return field.description || field.key;
}

function isBooleanField(field) {
  return !field.secret && ["true", "false"].includes(String(field.value || "").toLowerCase());
}

function currentFieldValue(field, control) {
  if (field.secret) return control.value.trim();
  if (control.type === "checkbox") return control.checked ? "true" : "false";
  return control.value;
}

function fieldChanged(field, control) {
  if (field.secret) return currentFieldValue(field, control) !== "";
  return currentFieldValue(field, control) !== String(field.value ?? "");
}

function changedFields() {
  const changed = {};
  for (const field of loadedFields) {
    const control = fieldControls.get(field.key);
    if (control && fieldChanged(field, control)) changed[field.key] = currentFieldValue(field, control);
  }
  return changed;
}

function updateDirtyState() {
  if (restartRequired) {
    if (dirtyEl) {
      dirtyEl.hidden = true;
      dirtyEl.textContent = "";
    }
    return;
  }
  const isDirty = Object.keys(changedFields()).length > 0;
  if (dirtyEl) {
    dirtyEl.hidden = !isDirty;
    dirtyEl.textContent = isDirty ? "Unsaved changes" : "";
  }
}

function setStatus(message) {
  if (statusEl) statusEl.textContent = message;
}

function notifyRestartRequiredChange() {
  if (restartRequiredChangeHandler) restartRequiredChangeHandler(restartRequired, { panelOpen: Boolean(activeContainer) });
}

function appendText(parent, text, tagName = "span") {
  const el = document.createElement(tagName);
  el.textContent = text;
  parent.appendChild(el);
  return el;
}

function renderField(field) {
  const row = document.createElement("div");
  const label = document.createElement("label");
  const input = document.createElement("input");
  const meta = document.createElement("div");

  label.textContent = fieldLabel(field);
  input.name = field.key;
  input.disabled = !field.editable || restartRequired;

  if (field.secret) {
    input.type = "password";
    input.value = "";
    input.placeholder = field.has_value ? "Enter replacement" : "Unset";
  } else if (isBooleanField(field)) {
    input.type = "checkbox";
    input.checked = String(field.value).toLowerCase() === "true";
  } else {
    input.type = "text";
    input.value = field.value ?? "";
  }

  input.addEventListener("input", updateDirtyState);
  input.addEventListener("change", updateDirtyState);
  fieldControls.set(field.key, input);

  appendText(meta, field.key);
  appendText(meta, field.secret ? (field.has_value ? " · value stored" : " · not set") : ` · ${field.value || "—"}`);
  if (field.restart_required) appendText(meta, " · restart required");

  row.append(label, input, meta);
  return row;
}

function renderMissingEnv(containerEl) {
  const message = document.createElement("p");
  message.textContent = ".env is required before operator settings can be edited.";
  containerEl.replaceChildren(message);
}

function renderPanel(containerEl, fields) {
  loadedFields = fields;
  fieldControls = new Map();

  const heading = document.createElement("h2");
  heading.textContent = "Settings";
  dirtyEl = document.createElement("p");
  dirtyEl.hidden = true;
  const form = document.createElement("form");
  const actions = document.createElement("div");
  const saveButton = document.createElement("button");
  const closeButton = document.createElement("button");
  const restartState = document.createElement("p");
  const restartButton = document.createElement("button");
  statusEl = document.createElement("p");

  for (const field of fields) form.appendChild(renderField(field));

  saveButton.type = "submit";
  saveButton.textContent = "Save";
  closeButton.type = "button";
  closeButton.textContent = "Close";
  closeButton.addEventListener("click", closeSettings);
  restartState.textContent = "Restart required.";
  restartState.hidden = !restartRequired;
  restartButton.type = "button";
  restartButton.textContent = "Restart";
  restartButton.hidden = !restartRequired;
  restartButton.addEventListener("click", restartBackend);
  saveButton.hidden = restartRequired;
  closeButton.hidden = restartRequired;
  actions.append(saveButton, closeButton, restartButton);
  form.appendChild(actions);
  form.addEventListener("submit", saveSettings);

  containerEl.replaceChildren(heading, dirtyEl, restartState, form, statusEl);
  updateDirtyState();
}

async function restartBackend() {
  if (!restartHandler) {
    setStatus("Restart unavailable.");
    return;
  }
  setStatus("Restarting.");
  try {
    await restartHandler();
    restartRequired = false;
    notifyRestartRequiredChange();
    if (activeContainer) await loadSettings(activeContainer);
  } catch (error) {
    setStatus("Restart failed.");
  }
}

async function saveSettings(event) {
  event.preventDefault();
  if (!writeConfigHandler) {
    setStatus("Save unavailable.");
    return;
  }
  const fields = changedFields();
  if (Object.keys(fields).length === 0) {
    setStatus("No changes to save.");
    return;
  }
  let payload;
  try {
    payload = await writeConfigHandler(fields);
  } catch (error) {
    setStatus("Save failed.");
    return;
  }
  restartRequired = true;
  notifyRestartRequiredChange();
  setStatus(`Saved: written ${payload.written?.length ?? 0}; rejected ${payload.rejected?.length ?? 0}.`);
  renderPanel(activeContainer, loadedFields);
}

async function loadSettings(containerEl) {
  if (!getConfigHandler) {
    const message = document.createElement("p");
    message.textContent = "Settings unavailable.";
    containerEl.replaceChildren(message);
    return;
  }
  let payload;
  try {
    payload = await getConfigHandler();
  } catch (error) {
    const message = document.createElement("p");
    message.textContent = "Settings unavailable.";
    containerEl.replaceChildren(message);
    return;
  }
  if (payload.detail?.error === "env_file_missing") {
    renderMissingEnv(containerEl);
    return;
  }
  renderPanel(containerEl, payload.fields || []);
}

export async function openSettings(containerEl, options = {}) {
  activeContainer = containerEl;
  restartHandler = options.restartBackend || restartHandler;
  restartRequiredChangeHandler = options.onRestartRequiredChange || restartRequiredChangeHandler;
  getConfigHandler = options.getOperatorConfig || getConfigHandler;
  writeConfigHandler = options.writeOperatorConfig || writeConfigHandler;
  containerEl.hidden = false;
  containerEl.textContent = "Loading settings…";
  notifyRestartRequiredChange();
  await loadSettings(containerEl);
}

export function closeSettings() {
  if (!activeContainer) return;
  activeContainer.hidden = true;
  activeContainer.replaceChildren();
  activeContainer = null;
  loadedFields = [];
  fieldControls = new Map();
  statusEl = null;
  dirtyEl = null;
  notifyRestartRequiredChange();
}
