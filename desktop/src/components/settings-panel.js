import { createAppearanceControls } from "./appearance-controls.js";
import { createRenderStateKeeper } from "./render-state.js";
import { appendText, button, buttonRow, field as labeledField } from "./ui/dom.js";
import { errorMessage } from "./ui/format.js";
import { renderPanelHeader } from "./ui/panel.js";

const restartScopes = new Set();

let activeContainer = null;
let keeper = null;
let loadedFields = [];
let fieldControls = new Map();
let statusEl = null;
let dirtyEl = null;
let settingsGeneration = 0;
let restartHandler = null;
let restartRequiredChangeHandler = null;
let getConfigHandler = null;
let writeConfigHandler = null;

export function restartScopeDisables(scopes, scope) {
  return [...(scopes || [])].includes(scope);
}

export function restartRequiredScopes() {
  return [...restartScopes];
}

export function clearRestartRequired() {
  restartScopes.clear();
  notifyRestartRequiredChange();
  if (activeContainer) renderPanel(activeContainer, loadedFields);
}

export function markRestartRequired(scope) {
  restartScopes.add(scope);
  notifyRestartRequiredChange();
  // Only the operator form is rendered here; a provider-scoped mark must not repaint it.
  if (activeContainer && scope === "operator") renderPanel(activeContainer, loadedFields);
}

function operatorRestartRequired() {
  return restartScopeDisables(restartScopes, "operator");
}

function anyRestartRequired() {
  return restartScopes.size > 0;
}

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
  if (operatorRestartRequired()) {
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

function setStatus(message, kind = "notice") {
  if (!statusEl) return;
  statusEl.textContent = message;
  statusEl.className = kind === "error" ? "panel-error" : "panel-notice";
}

function notifyRestartRequiredChange() {
  if (restartRequiredChangeHandler) {
    restartRequiredChangeHandler(anyRestartRequired(), { scopes: restartRequiredScopes() });
  }
}

function renderField(field, { hideDescription = false } = {}) {
  const input = Array.isArray(field.options) && field.options.length > 0 ? document.createElement("select") : document.createElement("input");

  input.name = field.key;
  input.disabled = !field.editable || operatorRestartRequired();
  // Secrets are never kept as drafts; everything else survives a re-render.
  if (!field.secret) input.dataset.draftKey = `setting:${field.key}`;

  if (field.secret) {
    input.type = "password";
    input.value = "";
    input.placeholder = field.has_value ? "Enter replacement" : "Unset";
  } else if (input.tagName === "SELECT") {
    for (const optionValue of field.options) {
      const option = document.createElement("option");
      option.value = optionValue;
      option.textContent = optionValue;
      input.appendChild(option);
    }
    input.value = field.value || field.options[0] || "";
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

  const help = [
    field.key,
    field.secret ? (field.has_value ? "value stored" : "not set") : `current ${field.value || "—"}`,
    field.restart_required ? "applies after restart" : "",
  ].filter(Boolean).join(" · ");
  if (input.type === "checkbox") {
    const label = document.createElement("label");
    label.className = "panel-choice";
    label.appendChild(input);
    appendText(label, fieldLabel(field));
    const row = document.createElement("div");
    row.className = "panel-field";
    row.appendChild(label);
    appendText(row, help, "span", "panel-help");
    return row;
  }
  const labelText = hideDescription ? "" : fieldLabel(field);
  return labeledField(labelText, input, { help });
}

function fieldSectionTitle(field) {
  return field.section || "Operator";
}

function groupedFields(fields) {
  const groups = [];
  for (const field of fields) {
    const title = fieldSectionTitle(field);
    let group = groups.find((candidate) => candidate.title === title);
    if (!group) {
      group = { title, primary: [], advanced: [] };
      groups.push(group);
    }
    if (field.advanced) group.advanced.push(field);
    else group.primary.push(field);
  }
  return groups;
}

function renderFieldGroup(group) {
  const section = document.createElement("section");
  const heading = document.createElement("h3");
  section.className = "settings-subsection";
  heading.textContent = group.title;
  section.appendChild(heading);
  for (const field of group.primary) section.appendChild(renderField(field));
  if (group.advanced.length > 0) {
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Advanced";
    details.appendChild(summary);
    for (const field of group.advanced) details.appendChild(renderField(field));
    section.appendChild(details);
  }
  return section;
}

function renderMessage(containerEl, text, kind = "panel-help") {
  const message = document.createElement("p");
  message.className = kind;
  message.textContent = text;
  containerEl.replaceChildren(renderPanelHeader("Settings"), message);
}

function renderMissingEnv(containerEl) {
  renderMessage(containerEl, "Create a .env file (copy .env.example) before operator settings can be edited.", "panel-error");
}

function renderPanel(containerEl, fields) {
  const visibleFields = (fields || []).filter((f) => !f.key.startsWith("REDIS_"));
  loadedFields = visibleFields;
  fieldControls = new Map();

  const appearance = createAppearanceControls();
  dirtyEl = document.createElement("p");
  dirtyEl.className = "panel-help";
  dirtyEl.hidden = true;
  const form = document.createElement("form");
  const restartState = document.createElement("p");
  restartState.className = "panel-notice";
  statusEl = document.createElement("p");
  statusEl.setAttribute("aria-live", "polite");

  const langField = visibleFields.find((f) => f.key === "JARVIS_LANGUAGE");
  const searxngEnable = visibleFields.find((f) => f.key === "USE_SEARXNG");
  const searxngPort = visibleFields.find((f) => f.key === "SEARXNG_PORT");
  const searxngUrl = visibleFields.find((f) => f.key === "SEARXNG_BASE_URL");
  const ddgsEnable = visibleFields.find((f) => f.key === "USE_DDGS");
  const tavilyEnable = visibleFields.find((f) => f.key === "USE_TAVILY");
  const tavilyKey = visibleFields.find((f) => f.key === "TAVILY_API_KEY");

  const isOperatorServicesLayout = Boolean(langField || searxngEnable || ddgsEnable || tavilyEnable);

  if (isOperatorServicesLayout) {
    const row1 = document.createElement("div");
    row1.className = "settings-row-2col";

    const langSection = document.createElement("section");
    langSection.className = "settings-subsection";
    const langHeading = document.createElement("h3");
    langHeading.textContent = "Display Language";
    langSection.appendChild(langHeading);
    if (langField) {
      langSection.appendChild(renderField(langField, { hideDescription: true }));
    }
    row1.append(langSection, appearance);
    form.appendChild(row1);

    if (searxngEnable || ddgsEnable || tavilyEnable || searxngPort || tavilyKey) {
      const searchHeading = document.createElement("h3");
      searchHeading.className = "settings-heading-separator";
      searchHeading.textContent = "Search Services";
      form.appendChild(searchHeading);

      if (searxngEnable || searxngPort) {
        const row3 = document.createElement("div");
        row3.className = "settings-service-row";
        const leftCol = document.createElement("div");
        leftCol.className = "settings-service-col";
        if (searxngEnable) leftCol.appendChild(renderField(searxngEnable));
        const rightCol = document.createElement("div");
        rightCol.className = "settings-service-col";
        if (searxngPort) rightCol.appendChild(renderField(searxngPort));
        if (searxngUrl) {
          const details = document.createElement("details");
          const summary = document.createElement("summary");
          summary.textContent = "Advanced URL";
          details.appendChild(summary);
          details.appendChild(renderField(searxngUrl));
          rightCol.appendChild(details);
        }
        row3.append(leftCol, rightCol);
        form.appendChild(row3);
      }

      if (ddgsEnable) {
        const row4 = document.createElement("div");
        row4.className = "settings-service-row";
        const leftCol = document.createElement("div");
        leftCol.className = "settings-service-col";
        leftCol.appendChild(renderField(ddgsEnable));
        const rightCol = document.createElement("div");
        rightCol.className = "settings-service-col settings-no-config";
        const noConfigText = document.createElement("span");
        noConfigText.textContent = "No configuration required";
        rightCol.appendChild(noConfigText);
        row4.append(leftCol, rightCol);
        form.appendChild(row4);
      }

      if (tavilyEnable || tavilyKey) {
        const row5 = document.createElement("div");
        row5.className = "settings-service-row";
        const leftCol = document.createElement("div");
        leftCol.className = "settings-service-col";
        if (tavilyEnable) leftCol.appendChild(renderField(tavilyEnable));
        const rightCol = document.createElement("div");
        rightCol.className = "settings-service-col";
        if (tavilyKey) rightCol.appendChild(renderField(tavilyKey));
        row5.append(leftCol, rightCol);
        form.appendChild(row5);
      }
    }

    const handledKeys = new Set([
      "JARVIS_LANGUAGE",
      "USE_SEARXNG",
      "SEARXNG_PORT",
      "SEARXNG_BASE_URL",
      "USE_DDGS",
      "USE_TAVILY",
      "TAVILY_API_KEY",
    ]);
    const otherFields = visibleFields.filter((f) => !handledKeys.has(f.key));
    if (otherFields.length > 0) {
      const grid = document.createElement("div");
      grid.className = "settings-grid";
      for (const group of groupedFields(otherFields)) grid.appendChild(renderFieldGroup(group));
      form.appendChild(grid);
    }
  } else {
    const grid = document.createElement("div");
    grid.className = "settings-grid";
    for (const group of groupedFields(visibleFields)) grid.appendChild(renderFieldGroup(group));
    form.append(appearance, grid);
  }

  restartState.textContent = "Saved changes apply after a backend restart.";
  restartState.hidden = !anyRestartRequired();
  const saveButton = button("Save", { type: "submit", focusKey: "settings:save" });
  saveButton.hidden = operatorRestartRequired();
  const restartButton = button("Restart backend", { variant: "primary", focusKey: "settings:restart", onClick: restartBackend });
  restartButton.hidden = !anyRestartRequired();
  form.appendChild(buttonRow(saveButton, restartButton));
  form.addEventListener("submit", saveSettings);

  const children = [renderPanelHeader("Settings"), dirtyEl, restartState, form, statusEl];
  if (keeper) keeper.render(...children);
  else containerEl.replaceChildren(...children);
  updateDirtyState();
}

async function restartBackend() {
  if (!restartHandler) {
    setStatus("Restart unavailable.");
    return;
  }
  setStatus("Restarting the backend…");
  try {
    await restartHandler();
    clearRestartRequired();
    if (activeContainer) await loadSettings(activeContainer);
  } catch (error) {
    setStatus(errorMessage(error, "Restart failed."), "error");
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
    setStatus(errorMessage(error, "Save failed."), "error");
    return;
  }
  // The saved values are now the known values, so a re-render shows them rather than the
  // values that were loaded before the save.
  const written = new Set(payload.written || []);
  loadedFields = loadedFields.map((item) => (
    written.has(item.key) && !item.secret ? { ...item, value: fields[item.key] } : item
  ));
  // markRestartRequired re-renders, which replaces statusEl, so report the outcome afterwards.
  markRestartRequired("operator");
  const rejected = payload.rejected?.length ?? 0;
  setStatus(
    rejected ? `Saved ${written.size}; ${rejected} could not be saved.` : `Saved ${written.size} setting${written.size === 1 ? "" : "s"}.`,
    rejected ? "error" : "notice",
  );
}

function settingsStale(request, containerEl) {
  return request !== settingsGeneration || activeContainer !== containerEl;
}

async function loadSettings(containerEl) {
  const request = ++settingsGeneration;
  if (!getConfigHandler) {
    renderMessage(containerEl, "Settings unavailable.", "panel-error");
    return;
  }
  let payload;
  try {
    payload = await getConfigHandler();
  } catch (error) {
    if (settingsStale(request, containerEl)) return;
    renderMessage(containerEl, errorMessage(error, "Settings unavailable."), "panel-error");
    return;
  }
  if (settingsStale(request, containerEl)) return;
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
  if (!keeper || keeper.container !== containerEl) keeper = Object.assign(createRenderStateKeeper(containerEl), { container: containerEl });
  containerEl.hidden = false;
  if (!loadedFields.length) renderMessage(containerEl, "Loading settings…");
  notifyRestartRequiredChange();
  await loadSettings(containerEl);
  keeper.release();
  containerEl.querySelector("h2")?.focus();
}

export function closeSettings() {
  if (!activeContainer) return;
  keeper?.retain();
  activeContainer.hidden = true;
  activeContainer.replaceChildren();
  activeContainer = null;
  settingsGeneration += 1;
  loadedFields = [];
  fieldControls = new Map();
  statusEl = null;
  dirtyEl = null;
  notifyRestartRequiredChange();
}
