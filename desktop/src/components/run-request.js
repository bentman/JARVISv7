// Operator controls for a live extension run: the answer form for a pending permission or
// input request, Approve/Decline for a run awaiting approval, and Cancel while it can still
// be stopped. `actions` supplies answer(runId, requestId, answer), decide(proposalId, outcome),
// cancel(proposalId), and notice(message).

export const ACTIVE_RUN_STATUSES = ["running", "awaiting_input", "awaiting_approval"];

function button(text, type = "button") {
  const node = document.createElement("button");
  node.type = type;
  node.textContent = text;
  return node;
}

function renderPermissionRequest(form, run, request, actions) {
  const options = document.createElement("select");
  options.dataset.draftKey = `${run.run_id}:${request.request_id}:option`;
  for (const option of request.options || []) {
    const entry = document.createElement("option");
    entry.value = option.optionId;
    entry.textContent = `${option.name} (${option.kind})`;
    options.appendChild(entry);
  }
  const accept = button("Accept", "submit");
  const decline = button("Decline");
  decline.addEventListener("click", () => actions.answer(run.run_id, request.request_id, { action: "decline" }));
  form.append(options, accept, decline);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    actions.answer(run.run_id, request.request_id, { action: "accept", option_id: options.value });
  });
}

function renderInputRequest(form, run, request, actions) {
  const schema = request.requestedSchema || {};
  const fields = schema.properties || {};
  const complex = Object.values(fields).some((item) => ["object", "array"].includes(item.type));
  const inputs = [];
  if (complex) {
    const json = document.createElement("textarea");
    json.dataset.draftKey = `${run.run_id}:${request.request_id}:$json`;
    json.placeholder = "Advanced JSON response";
    json.required = true;
    form.appendChild(json);
    inputs.push(["$json", json, { type: "json" }]);
  }
  const message = document.createElement("p");
  message.className = "extensions-row-meta";
  message.textContent = request.message || "This operation needs your input.";
  form.appendChild(message);
  for (const [name, item] of complex ? [] : Object.entries(fields)) {
    const input = Array.isArray(item.enum) ? document.createElement("select") : document.createElement("input");
    input.dataset.draftKey = `${run.run_id}:${request.request_id}:${name}`;
    input.placeholder = name;
    input.required = (schema.required || []).includes(name);
    if (Array.isArray(item.enum)) {
      for (const value of item.enum) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        input.appendChild(option);
      }
    } else {
      input.type = item.type === "boolean" ? "checkbox" : item.type === "number" || item.type === "integer" ? "number" : "text";
    }
    form.appendChild(input);
    inputs.push([name, input, item]);
  }
  const submit = button("Send", "submit");
  const decline = button("Cancel");
  decline.addEventListener("click", () => actions.answer(run.run_id, request.request_id, { action: "decline" }));
  form.append(submit, decline);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    try {
      const content = inputs[0]?.[0] === "$json"
        ? JSON.parse(inputs[0][1].value)
        : Object.fromEntries(inputs.map(([name, input, item]) => [
          name,
          item.type === "boolean" ? input.checked : item.type === "number" || item.type === "integer" ? Number(input.value) : input.value,
        ]));
      actions.answer(run.run_id, request.request_id, { action: "accept", content });
    } catch {
      actions.notice("Response must be valid JSON.");
    }
  });
}

export function appendRunControls(block, run, actions) {
  if (run.request) {
    const form = document.createElement("form");
    if (run.request.kind === "permission_request") renderPermissionRequest(form, run, run.request, actions);
    else renderInputRequest(form, run, run.request, actions);
    block.appendChild(form);
  }
  if (run.status === "awaiting_approval" && run.proposal_id) {
    const approve = button("Approve");
    approve.addEventListener("click", () => actions.decide(run.proposal_id, "approved"));
    const decline = button("Decline");
    decline.addEventListener("click", () => actions.decide(run.proposal_id, "denied"));
    block.append(approve, decline);
  }
  if (ACTIVE_RUN_STATUSES.includes(run.status) && run.proposal_id) {
    const cancel = button("Cancel");
    cancel.addEventListener("click", () => actions.cancel(run.proposal_id));
    block.appendChild(cancel);
  }
}
