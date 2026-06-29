const SERVICE_LABELS = {
  redis: "Redis",
  searxng: "SearXNG",
};

function serviceLabel(name) {
  return SERVICE_LABELS[name] || name;
}

function statusText(status) {
  return status?.reachable ? "reachable" : "unavailable";
}

function searxngDetail(status) {
  const reason = String(status?.reason || "unknown");
  const container = reason.includes("container reachable") || status?.reachable ? "container reachable" : "container unavailable";
  const json = reason.includes("json usable") ? "json usable" : "json not enabled";
  return `${container}; ${json}`;
}

function serviceDetail(name, status) {
  if (name === "redis") {
    return status?.reachable && status?.endpoint ? status.endpoint : status?.reason || "unknown";
  }
  if (name === "searxng") {
    return searxngDetail(status);
  }
  return status?.reason || "unknown";
}

function renderLine(name, status) {
  const row = document.createElement("div");
  const label = document.createElement("strong");
  const state = document.createElement("span");
  const divider = document.createElement("span");
  const detail = document.createElement("span");

  row.className = "service-status-row";
  state.className = "service-status-state";
  state.dataset.status = status?.reachable ? "reachable" : "unavailable";
  divider.className = "service-status-divider";
  detail.className = "service-status-detail";

  label.textContent = `${serviceLabel(name)}: `;
  state.textContent = statusText(status);
  divider.textContent = " • ";
  detail.textContent = serviceDetail(name, status);

  row.append(label, state, divider, detail);
  return row;
}

export function renderServiceStatus(servicesPayload, containerEl) {
  if (!servicesPayload) {
    containerEl.textContent = "Service status unavailable.";
    return;
  }

  const rows = [];
  for (const name of ["redis", "searxng"]) {
    rows.push(renderLine(name, servicesPayload[name]));
  }
  containerEl.replaceChildren(...rows);
}
