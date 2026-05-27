const SERVICE_LABELS = {
  redis: "Redis",
  searxng: "SearXNG",
};

function serviceLabel(name) {
  return SERVICE_LABELS[name] || name;
}

function renderLine(name, status) {
  const row = document.createElement("div");
  const label = document.createElement("strong");
  const detail = document.createElement("span");
  const reachable = Boolean(status?.reachable);

  label.textContent = `${serviceLabel(name)}: `;
  detail.textContent = `${reachable ? "reachable" : "unreachable"} · ${status?.reason || "unknown"}`;
  row.append(label, detail);
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