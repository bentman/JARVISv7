function appendField(containerEl, label, value) {
  const row = document.createElement("div");
  row.className = "wake-indicator-field";

  const labelEl = document.createElement("span");
  labelEl.className = "wake-indicator-label";
  labelEl.textContent = label;

  const valueEl = document.createElement("span");
  valueEl.className = "wake-indicator-value";
  valueEl.textContent = value;

  row.append(labelEl, valueEl);
  containerEl.appendChild(row);
}

export function renderWakeStatus(wakePayload, containerEl) {
  if (!containerEl) return;

  containerEl.replaceChildren();

  const provider = wakePayload?.provider || "unknown";
  const available = Boolean(wakePayload?.available);
  const monitoring = Boolean(wakePayload?.monitoring);
  const reason = wakePayload?.reason || "not provided";

  const summary = document.createElement("p");
  summary.className = "wake-indicator-summary";
  if (available && monitoring) {
    summary.textContent = `Wake monitoring active via ${provider}.`;
  } else if (available) {
    summary.textContent = `Wake provider ${provider} is available; manual PTT is active.`;
  } else {
    summary.textContent = `Manual PTT only; wake provider ${provider} is unavailable.`;
  }

  const fields = document.createElement("div");
  fields.className = "wake-indicator-fields";
  appendField(fields, "provider", provider);
  appendField(fields, "available", String(available));
  appendField(fields, "monitoring", String(monitoring));
  appendField(fields, "reason", reason);

  containerEl.dataset.available = String(available);
  containerEl.dataset.monitoring = String(monitoring);
  containerEl.append(summary, fields);
}