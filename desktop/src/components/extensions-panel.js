function errorMessage(error, fallback) {
  return error?.detail?.message || error?.message || fallback;
}

function isConflict(error) {
  return error?.status === 409 || error?.detail?.error === "conflict";
}

export function extensionStateEnabled(extension, mutationPending) {
  // The backend owns which transitions are legal; the renderer only avoids double-submits
  // and does not resurrect a retired extension it was already told about.
  return Boolean(extension?.extension_id) && !mutationPending && extension.state !== "retired";
}

export function extensionActivityState(extension) {
  if (!extension) return "idle";
  if (extension.state === "retired") return "retired";
  if (extension.state === "disabled") return "blocked";
  if (extension.availability !== "available") return "blocked";
  if (extension.readiness === "degraded") return "degraded";
  return "ready";
}

export function formatExtensionOrigin(extension) {
  if (!extension) return "";
  return `${extension.family} · ${extension.trust} · v${extension.version}`;
}

export function requestedCapabilities(extension) {
  const claims = extension?.metadata_claims?.requested_capabilities;
  return Array.isArray(claims?.ids) ? claims.ids : [];
}

function copyState(state) {
  return {
    ...state,
    catalog: state.catalog
      ? { ...state.catalog, extensions: [...(state.catalog.extensions || [])] }
      : null,
    errors: [...state.errors],
    detail: state.detail ? { ...state.detail } : null,
  };
}

export function createExtensionsPanelController(handlers, render = () => undefined) {
  const state = {
    catalog: null,
    errors: [],
    detail: null,
    body: "",
    selectedExtensionId: "",
    familyFilter: "",
    catalogLoading: false,
    errorsLoading: false,
    detailLoading: false,
    mutationPending: false,
    catalogError: "",
    errorsError: "",
    detailError: "",
    conflict: "",
    notice: "",
    runtime: null,
    runs: [],
  };
  let catalogSequence = 0;
  let errorsSequence = 0;
  let detailSequence = 0;

  function emit() {
    render(copyState(state));
  }

  async function refreshCatalog() {
    if (!handlers.getExtensions) return null;
    const request = ++catalogSequence;
    state.catalogLoading = true;
    state.catalogError = "";
    emit();
    try {
      const payload = await handlers.getExtensions();
      if (request !== catalogSequence) return null;
      state.catalog = payload;
      return payload;
    } catch (error) {
      if (request !== catalogSequence) return null;
      state.catalogError = errorMessage(error, "The extension catalog is unavailable.");
      return null;
    } finally {
      if (request === catalogSequence) {
        state.catalogLoading = false;
        emit();
      }
    }
  }

  async function refreshErrors() {
    if (!handlers.getExtensionErrors) return null;
    const request = ++errorsSequence;
    state.errorsLoading = true;
    state.errorsError = "";
    emit();
    try {
      const payload = await handlers.getExtensionErrors();
      if (request !== errorsSequence) return null;
      state.errors = payload?.errors || [];
      return payload;
    } catch (error) {
      if (request !== errorsSequence) return null;
      state.errorsError = errorMessage(error, "Extension load errors are unavailable.");
      return null;
    } finally {
      if (request === errorsSequence) {
        state.errorsLoading = false;
        emit();
      }
    }
  }

  async function selectExtension(extensionId) {
    if (!handlers.getExtensionDetail) return null;
    const request = ++detailSequence;
    state.selectedExtensionId = extensionId;
    state.detailLoading = true;
    state.detailError = "";
    state.body = "";
    emit();
    try {
      const payload = await handlers.getExtensionDetail(extensionId);
      if (request !== detailSequence) return null;
      state.detail = payload;
      if (handlers.getExtensionRuntime) state.runtime = await handlers.getExtensionRuntime(extensionId);
      if (handlers.getExtensionRuns) state.runs = (await handlers.getExtensionRuns())?.runs || [];
      return payload;
    } catch (error) {
      if (request !== detailSequence) return null;
      state.detailError = errorMessage(error, "That extension is unavailable.");
      return null;
    } finally {
      if (request === detailSequence) {
        state.detailLoading = false;
        emit();
      }
    }
  }

  async function invoke(extensionId, capabilityId, argumentsValue) {
    try {
      const result = await handlers.invokeExtension(extensionId, capabilityId, argumentsValue);
      state.notice = result?.status === "awaiting_approval" ? "Awaiting approval." : "Extension invoked.";
      if (handlers.getExtensionRuns) state.runs = (await handlers.getExtensionRuns())?.runs || [];
      emit();
      return result;
    } catch (error) { state.detailError = errorMessage(error, "Extension invocation failed."); emit(); return null; }
  }

  async function answer(runId, requestId, answerValue) {
    try { await handlers.answerExtensionInput(runId, requestId, answerValue); }
    catch (error) { state.detailError = errorMessage(error, "Extension input was not accepted."); emit(); return; }
    if (handlers.getExtensionRuns) state.runs = (await handlers.getExtensionRuns())?.runs || [];
    emit();
  }

  async function credential(extensionId, name, secret) {
    try { await handlers.writeExtensionCredential(extensionId, name, secret); }
    catch (error) { state.detailError = errorMessage(error, "Credential was not stored."); emit(); return; }
    state.notice = "Credential stored.";
    emit();
  }

  async function refreshRuns() {
    if (!handlers.getExtensionRuns) return;
    state.runs = (await handlers.getExtensionRuns())?.runs || [];
    emit();
  }

  async function decide(proposalId, outcome) {
    await handlers.decideAction(proposalId, outcome);
    await refreshRuns();
  }

  async function cancel(proposalId) {
    await handlers.cancelAction(proposalId);
    await refreshRuns();
  }

  async function loadBody(extensionId) {
    if (!handlers.getExtensionBody) return null;
    const request = detailSequence;
    try {
      const payload = await handlers.getExtensionBody(extensionId);
      if (request !== detailSequence) return null;
      state.body = payload?.body || "";
      return payload;
    } catch (error) {
      if (request !== detailSequence) return null;
      state.detailError = errorMessage(error, "That extension has no readable body.");
      return null;
    } finally {
      if (request === detailSequence) emit();
    }
  }

  async function setState(extensionId, nextState, reason = null) {
    if (state.mutationPending) return null;
    state.mutationPending = true;
    state.conflict = "";
    state.notice = "";
    state.detailError = "";
    emit();
    try {
      const current = state.detail?.revision ?? null;
      const payload = await handlers.setExtensionState(extensionId, nextState, current, reason);
      state.detail = payload;
      state.notice = `Extension ${nextState}.`;
      await refreshCatalog();
      return payload;
    } catch (error) {
      if (isConflict(error)) {
        state.conflict = `${errorMessage(error, "That change was not applied.")} The extension was reloaded.`;
      } else {
        state.detailError = errorMessage(error, "That extension could not be changed.");
      }
      await refreshCatalog();
      await selectExtension(extensionId);
      return null;
    } finally {
      state.mutationPending = false;
      emit();
    }
  }

  function filterFamily(family) {
    state.familyFilter = family;
    emit();
  }

  function notice(message) {
    state.notice = message;
    emit();
  }

  async function load() {
    await Promise.all([refreshCatalog(), refreshErrors()]);
  }

  function cancelPendingReads() {
    catalogSequence += 1;
    errorsSequence += 1;
    detailSequence += 1;
    state.catalogLoading = false;
    state.errorsLoading = false;
    state.detailLoading = false;
  }

  emit();
  return {
    load,
    refreshCatalog,
    refreshErrors,
    selectExtension,
    loadBody,
    setState,
    filterFamily,
    invoke,
    answer,
    credential,
    refreshRuns,
    decide,
    cancel,
    notice,
    cancelPendingReads,
    snapshot: () => copyState(state),
  };
}

function appendText(parent, text, tagName = "span", className = "") {
  const node = document.createElement(tagName);
  node.textContent = text;
  if (className) node.className = className;
  parent.appendChild(node);
  return node;
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

function labeledValue(parent, label, value) {
  const field = document.createElement("div");
  field.className = "extensions-field";
  appendText(field, label, "dt");
  appendText(field, formatValue(value), "dd");
  parent.appendChild(field);
  return field;
}

function renderCatalog(state) {
  const section = document.createElement("section");
  section.className = "extensions-section";
  appendText(section, "Installed extensions", "h3");
  if (state.catalogLoading) {
    appendText(section, "Loading extensions…", "p", "extensions-help");
    return section;
  }
  if (state.catalogError) {
    appendText(section, state.catalogError, "p", "extensions-error");
    return section;
  }
  const extensions = state.catalog?.extensions || [];
  if (!extensions.length) {
    appendText(section, "No extensions are registered.", "p", "extensions-help");
    return section;
  }

  const families = Object.entries(state.catalog?.families || {});
  if (families.length) {
    const filters = document.createElement("div");
    filters.className = "extensions-buttons";
    for (const [family, count] of [["", extensions.length], ...families]) {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = family ? `${family} (${count})` : `all (${count})`;
      button.setAttribute("aria-pressed", String(state.familyFilter === family));
      button.addEventListener("click", () => state.actions.filterFamily(family));
      filters.appendChild(button);
    }
    section.appendChild(filters);
  }

  const list = document.createElement("ul");
  list.className = "extensions-list";
  for (const extension of extensions) {
    if (state.familyFilter && extension.family !== state.familyFilter) continue;
    const item = document.createElement("li");
    const row = document.createElement("button");
    row.type = "button";
    row.className = "extensions-row";
    row.dataset.state = extensionActivityState(extension);
    row.setAttribute("aria-pressed", String(state.selectedExtensionId === extension.extension_id));
    appendText(row, extension.display_name, "strong");
    appendText(row, extension.extension_id, "span", "extensions-row-meta");
    appendText(row, formatExtensionOrigin(extension), "span", "extensions-row-meta");
    row.addEventListener("click", () => state.actions.selectExtension(extension.extension_id));
    item.appendChild(row);
    if (extension.unavailable_explanation) {
      appendText(item, extension.unavailable_explanation, "p", "extensions-help");
    }
    for (const collision of extension.collisions || []) {
      appendText(item, collision, "p", "extensions-error");
    }
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

function renderDetail(state) {
  const section = document.createElement("section");
  section.className = "extensions-section";
  appendText(section, "Detail", "h3");
  if (state.detailLoading) {
    appendText(section, "Loading extension…", "p", "extensions-help");
    return section;
  }
  if (state.detailError) {
    appendText(section, state.detailError, "p", "extensions-error");
    return section;
  }
  if (!state.detail) {
    appendText(section, "Select an extension to inspect it.", "p", "extensions-help");
    return section;
  }
  const detail = state.detail;
  const status = appendText(section, detail.state, "p", "extensions-status");
  status.dataset.state = extensionActivityState(detail);

  const facts = document.createElement("dl");
  facts.className = "extensions-facts";
  labeledValue(facts, "Identifier", detail.extension_id);
  labeledValue(facts, "Family", detail.family);
  labeledValue(facts, "Version", detail.version);
  labeledValue(facts, "Source", detail.source);
  labeledValue(facts, "Provenance", detail.provenance);
  labeledValue(facts, "Trust", detail.trust);
  labeledValue(facts, "Readiness", detail.readiness);
  labeledValue(facts, "Availability", detail.availability);
  labeledValue(facts, "Revision", detail.revision);
  section.appendChild(facts);

  const requested = requestedCapabilities(detail);
  if (requested.length) {
    const block = document.createElement("div");
    block.className = "extensions-requested";
    appendText(block, "Requested capabilities", "h4");
    appendText(
      block,
      "These are requests recorded for you, not permissions this extension holds.",
      "p",
      "extensions-help",
    );
    const list = document.createElement("ul");
    list.className = "extensions-list";
    for (const capability of requested) {
      const item = document.createElement("li");
      appendText(item, capability);
      list.appendChild(item);
    }
    block.appendChild(list);
    section.appendChild(block);
  }

  const buttons = document.createElement("div");
  buttons.className = "extensions-buttons";
  const enabled = extensionStateEnabled(detail, state.mutationPending);
  for (const next of ["enabled", "disabled", "retired"]) {
    if (next === detail.state) continue;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = next === "retired" ? "Retire" : `Set ${next}`;
    button.disabled = !enabled;
    button.addEventListener("click", () => state.actions.setState(detail.extension_id, next));
    buttons.appendChild(button);
  }
  if (detail.body_available) {
    const body = document.createElement("button");
    body.type = "button";
    body.textContent = "Show body";
    body.disabled = state.mutationPending;
    body.addEventListener("click", () => state.actions.loadBody(detail.extension_id));
    buttons.appendChild(body);
  }
  section.appendChild(buttons);

  if (state.runtime?.operations?.length) {
    const runtime = document.createElement("div");
    runtime.className = "extensions-requested";
    appendText(runtime, "Operations", "h4");
    for (const operation of state.runtime.operations) {
      const form = document.createElement("form");
      appendText(form, operation.name, "strong");
      const fields = operation.input_schema?.properties || {};
      const complex = Object.values(fields).some((schema) => ["object", "array"].includes(schema.type));
      const inputs = [];
      if (complex) {
        const json = document.createElement("textarea");
        json.dataset.draftKey = `${detail.extension_id}:${operation.capability_id}:$json`;
        json.placeholder = "Advanced JSON arguments";
        json.required = true;
        form.appendChild(json);
        inputs.push(["$json", json, { type: "json" }]);
      }
      for (const [name, schema] of complex ? [] : Object.entries(fields)) {
        const input = document.createElement("input");
        input.dataset.draftKey = `${detail.extension_id}:${operation.capability_id}:${name}`;
        input.name = name;
        input.required = (operation.input_schema?.required || []).includes(name);
        if (Array.isArray(schema.enum)) { const select = document.createElement("select"); select.dataset.draftKey = input.dataset.draftKey; for (const value of schema.enum) { const option = document.createElement("option"); option.value = value; option.textContent = value; select.appendChild(option); } inputs.push([name, select, schema]); form.appendChild(select); continue; }
        input.type = schema.type === "boolean" ? "checkbox" : schema.type === "number" || schema.type === "integer" ? "number" : "text";
        input.placeholder = name;
        form.appendChild(input);
        inputs.push([name, input, schema]);
      }
      const submit = document.createElement("button");
      submit.type = "submit";
      submit.textContent = "Invoke";
      submit.disabled = !operation.available;
      form.appendChild(submit);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        let argumentsValue;
        try {
          argumentsValue = inputs[0]?.[0] === "$json" ? JSON.parse(inputs[0][1].value) : Object.fromEntries(inputs.map(([name, input, schema]) => [name, schema.type === "boolean" ? input.checked : schema.type === "number" || schema.type === "integer" ? Number(input.value) : input.value]));
        } catch {
          state.actions.notice("Arguments must be valid JSON.");
          return;
        }
        state.actions.invoke(detail.extension_id, operation.capability_id, argumentsValue);
      });
      runtime.appendChild(form);
    }
    if (detail.family === "mcp") {
      const credential = document.createElement("form");
      appendText(credential, "Credential", "strong");
      const name = document.createElement("input"); name.placeholder = "name"; name.required = true;
      const secret = document.createElement("input"); secret.type = "password"; secret.placeholder = "secret"; secret.required = true;
      const save = document.createElement("button"); save.type = "submit"; save.textContent = "Store credential";
      credential.append(name, secret, save);
      credential.addEventListener("submit", (event) => { event.preventDefault(); state.actions.credential(detail.extension_id, name.value, secret.value); secret.value = ""; });
      runtime.appendChild(credential);
    }
    section.appendChild(runtime);
  }
  const runs = state.runs.filter((run) => run.extension_id === detail.extension_id);
  if (runs.length) {
    const block = document.createElement("div"); block.className = "extensions-requested";
    appendText(block, "Runs", "h4");
    for (const run of runs) {
      appendText(block, `${run.status} · ${run.run_id}`, "strong");
      if (run.request) {
        const form = document.createElement("form");
        const request = run.request;
        if (request.kind === "permission_request") {
          const options = document.createElement("select"); options.dataset.draftKey = `${run.run_id}:${request.request_id}:option`;
          for (const option of request.options || []) {
            const entry = document.createElement("option"); entry.value = option.optionId; entry.textContent = `${option.name} (${option.kind})`; options.appendChild(entry);
          }
          const accept = document.createElement("button"); accept.type = "submit"; accept.textContent = "Accept";
          const decline = document.createElement("button"); decline.type = "button"; decline.textContent = "Decline";
          decline.addEventListener("click", () => state.actions.answer(run.run_id, request.request_id, { action: "decline" }));
          form.append(options, accept, decline);
          form.addEventListener("submit", (event) => { event.preventDefault(); state.actions.answer(run.run_id, request.request_id, { action: "accept", option_id: options.value }); });
        } else {
          const schema = request.requestedSchema || {};
          const fields = schema.properties || {};
          const complex = Object.values(fields).some((item) => ["object", "array"].includes(item.type));
          const inputs = [];
          if (complex) { const json = document.createElement("textarea"); json.dataset.draftKey = `${run.run_id}:${request.request_id}:$json`; json.placeholder = "Advanced JSON response"; json.required = true; form.appendChild(json); inputs.push(["$json", json, { type: "json" }]); }
          appendText(form, JSON.stringify({ message: request.message, tool_call: request.tool_call }), "p", "extensions-row-meta");
          for (const [name, item] of complex ? [] : Object.entries(fields)) { const input = Array.isArray(item.enum) ? document.createElement("select") : document.createElement("input"); input.dataset.draftKey = `${run.run_id}:${request.request_id}:${name}`; input.placeholder = name; input.required = (schema.required || []).includes(name); if (Array.isArray(item.enum)) for (const value of item.enum) { const option = document.createElement("option"); option.value = value; option.textContent = value; input.appendChild(option); } else input.type = item.type === "boolean" ? "checkbox" : item.type === "number" || item.type === "integer" ? "number" : "text"; form.appendChild(input); inputs.push([name, input, item]); }
          const submit = document.createElement("button"); submit.type = "submit"; submit.textContent = "Send"; const decline = document.createElement("button"); decline.type = "button"; decline.textContent = "Cancel"; decline.addEventListener("click", () => state.actions.answer(run.run_id, request.request_id, { action: "decline" })); form.append(submit, decline);
          form.addEventListener("submit", (event) => { event.preventDefault(); try { const content = inputs[0]?.[0] === "$json" ? JSON.parse(inputs[0][1].value) : Object.fromEntries(inputs.map(([name, input, item]) => [name, item.type === "boolean" ? input.checked : item.type === "number" || item.type === "integer" ? Number(input.value) : input.value])); state.actions.answer(run.run_id, request.request_id, { action: "accept", content }); } catch { state.actions.notice("Response must be valid JSON."); } });
        }
        block.appendChild(form);
      }
      if (run.status === "awaiting_approval" && run.proposal_id) {
        const approve = document.createElement("button"); approve.type = "button"; approve.textContent = "Approve"; approve.addEventListener("click", () => state.actions.decide(run.proposal_id, "approved"));
        const decline = document.createElement("button"); decline.type = "button"; decline.textContent = "Decline"; decline.addEventListener("click", () => state.actions.decide(run.proposal_id, "denied")); block.append(approve, decline);
      }
      if (["running", "awaiting_input", "awaiting_approval"].includes(run.status) && run.proposal_id) { const cancel = document.createElement("button"); cancel.type = "button"; cancel.textContent = "Cancel"; cancel.addEventListener("click", () => state.actions.cancel(run.proposal_id)); block.appendChild(cancel); }
      if (run.events?.length) appendText(block, JSON.stringify(run.events.at(-1)), "p", "extensions-row-meta");
      if (run.result) appendText(block, JSON.stringify(run.result), "p", "extensions-row-meta");
    }
    section.appendChild(block);
  }

  if (state.body) {
    const body = document.createElement("details");
    body.open = true;
    appendText(body, "Body", "summary");
    appendText(body, state.body, "pre");
    section.appendChild(body);
  }
  return section;
}

function renderErrors(state) {
  const section = document.createElement("section");
  section.className = "extensions-section";
  appendText(section, "Load errors", "h3");
  if (state.errorsLoading) {
    appendText(section, "Loading errors…", "p", "extensions-help");
    return section;
  }
  if (state.errorsError) {
    appendText(section, state.errorsError, "p", "extensions-error");
    return section;
  }
  if (!state.errors.length) {
    appendText(section, "Every extension loaded cleanly.", "p", "extensions-help");
    return section;
  }
  const list = document.createElement("ul");
  list.className = "extensions-list";
  for (const error of state.errors) {
    const item = document.createElement("li");
    appendText(item, `${error.family} · ${error.source}`, "strong");
    appendText(item, error.reason, "span", "extensions-row-meta");
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

function renderPanel(container, state, actions) {
  const drafts = new Map([...container.querySelectorAll("[data-draft-key]")].map((field) => [field.dataset.draftKey, { value: field.value, checked: field.checked, focused: document.activeElement === field }]));
  const view = { ...state, actions };
  const header = document.createElement("div");
  header.className = "extensions-panel-header";
  const heading = appendText(header, "Extensions", "h2");
  heading.tabIndex = -1;
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Close";
  close.addEventListener("click", () => actions.close());
  header.appendChild(close);

  const messages = document.createElement("div");
  messages.setAttribute("aria-live", "polite");
  for (const message of [state.conflict, state.notice]) {
    if (message) {
      appendText(
        messages,
        message,
        "p",
        message === state.notice ? "extensions-notice" : "extensions-error",
      );
    }
  }

  container.replaceChildren(
    header,
    messages,
    renderCatalog(view),
    renderDetail(view),
    renderErrors(view),
  );
  for (const field of container.querySelectorAll("[data-draft-key]")) {
    const draft = drafts.get(field.dataset.draftKey);
    if (!draft) continue;
    field.value = draft.value;
    if (field.type === "checkbox") field.checked = draft.checked;
    if (draft.focused) field.focus();
  }
}

export function createExtensionsPanel(container, handlers, options = {}) {
  let open = false;
  let controller;
  const actions = {
    close: () => close(),
    selectExtension: (extensionId) => controller.selectExtension(extensionId),
    loadBody: (extensionId) => controller.loadBody(extensionId),
    setState: (extensionId, next) => controller.setState(extensionId, next),
    filterFamily: (family) => controller.filterFamily(family),
    invoke: (extensionId, capabilityId, argumentsValue) => controller.invoke(extensionId, capabilityId, argumentsValue),
    answer: (runId, requestId, answerValue) => controller.answer(runId, requestId, answerValue),
    credential: (extensionId, name, secret) => controller.credential(extensionId, name, secret),
    decide: (proposalId, outcome) => controller.decide(proposalId, outcome),
    cancel: (proposalId) => controller.cancel(proposalId),
    notice: (message) => controller.notice(message),
  };
  controller = createExtensionsPanelController(handlers, (state) => {
    if (open) renderPanel(container, state, actions);
  });

  async function show() {
    open = true;
    container.hidden = false;
    renderPanel(container, controller.snapshot(), actions);
    await controller.load();
    polling = window.setInterval(() => {
      const active = document.activeElement;
      if (active && ["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName)) return;
      controller.refreshRuns();
    }, 1000);
    container.querySelector("h2")?.focus();
  }

  function close() {
    if (!open) return;
    open = false;
    controller.cancelPendingReads();
    if (polling) { window.clearInterval(polling); polling = null; }
    container.hidden = true;
    container.replaceChildren();
    options.onClose?.();
  }

  let polling = null;
  return { open: show, close, isOpen: () => open, controller };
}
