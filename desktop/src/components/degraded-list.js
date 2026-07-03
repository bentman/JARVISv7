const OPTIONAL_SERVICE_LABELS = {
  redis: "Optional Redis Cache",
  searxng: "Optional SearXNG Search",
};
const LOCAL_RUNTIME_FALLBACK_REASON = ["local runtime", "unavailable"].join(" ");

function isOllamaLocalRuntimeFallback(family, readinessPayload) {
  return (
    family?.family === "llm" &&
    String(readinessPayload?.active_llm_runtime || "").toLowerCase() === "ollama" &&
    String(family?.reason || "").toLowerCase() === LOCAL_RUNTIME_FALLBACK_REASON
  );
}

function familyLabel(name) {
  return String(name || "unknown").toUpperCase();
}

function addCondition(rows, kind, title, detail) {
  const cleanDetail = String(detail || "").trim();
  if (!cleanDetail) return;
  rows.push({ kind, title, detail: cleanDetail });
}

export function collectDegradedConditions(readinessPayload) {
  const rows = [];
  if (!readinessPayload || typeof readinessPayload !== "object") return rows;

  if (readinessPayload.status !== "ready" && readinessPayload?.preflight?.probe_error_count > 0) {
    addCondition(
      rows,
      "backend",
      "Backend readiness degraded",
      `${readinessPayload.preflight.probe_error_count} preflight probe error(s) reported by /readiness.`,
    );
  }

  for (const family of selectedFamilyBlockers(readinessPayload)) {
    addCondition(
      rows,
      "family",
      `${familyLabel(family.family)} selected path not ready`,
      family.reason || `${familyLabel(family.family)} readiness is unavailable.`,
    );
  }

  for (const reason of readinessPayload.resident_audio?.degraded_reasons || []) {
    addCondition(rows, "resident-audio", "Resident audio degraded", reason);
  }

  for (const [name, status] of Object.entries(readinessPayload.services || {})) {
    if (status?.reachable) continue;
    addCondition(
      rows,
      "optional-service",
      `${OPTIONAL_SERVICE_LABELS[name] || `Optional ${name}`} unavailable`,
      status?.reason || "optional service is unavailable",
    );
  }

  return rows;
}

export function selectedFamilyBlockers(readinessPayload) {
  if (!readinessPayload || typeof readinessPayload !== "object") return [];
  return Object.values(readinessPayload.families || {}).filter(
    (family) => !family?.ready && !isOllamaLocalRuntimeFallback(family, readinessPayload),
  );
}

function renderCondition(row) {
  const item = document.createElement("li");
  const title = document.createElement("strong");
  const detail = document.createElement("span");

  item.className = "degraded-condition";
  item.dataset.kind = row.kind;
  title.textContent = row.title;
  detail.textContent = row.detail;

  item.append(title, detail);
  return item;
}

export function renderDegradedList(readinessPayload, containerEl) {
  if (!containerEl) return;

  containerEl.replaceChildren();
  const detailEl = containerEl.closest("details");
  const rows = collectDegradedConditions(readinessPayload);

  if (rows.length === 0) {
    containerEl.hidden = true;
    if (detailEl) {
      detailEl.hidden = true;
      detailEl.open = false;
    }
    return;
  }

  const list = document.createElement("ul");
  list.className = "degraded-condition-list";
  for (const row of rows) {
    list.appendChild(renderCondition(row));
  }

  containerEl.hidden = false;
  if (detailEl) detailEl.hidden = false;
  containerEl.appendChild(list);
}
