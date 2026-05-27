const FAMILY_ORDER = ["llm", "stt", "tts", "wake"];

const FAMILY_LABELS = {
  stt: "STT",
  tts: "TTS",
  llm: "LLM",
  wake: "Wake",
  ptt: "PTT",
};

const FAILED_REASON_TOKENS = ["MISSING", "unavailable"];

function isOllamaLocalRuntimeFallback(family, activeLlmRuntime) {
  return (
    family?.family === "llm" &&
    String(activeLlmRuntime || "").toLowerCase() === "ollama" &&
    String(family?.reason || "").toLowerCase() === "local runtime unavailable"
  );
}

function appendFactList(payload, containerEl) {
  const facts = document.createElement("dl");
  facts.className = "facts readiness-summary";

  for (const [label, value] of [
    ["Arch", payload?.arch],
    ["Profile", payload?.profile_id],
    ["LLM", payload?.active_llm_runtime],
    ["Status", payload?.status],
  ]) {
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value || "unknown";
    facts.append(term, detail);
  }

  containerEl.appendChild(facts);
}

function orderedFamilies(families) {
  const entries = families || {};
  const ordered = FAMILY_ORDER.filter((name) => entries[name]).map((name) => entries[name]);
  const remaining = Object.keys(entries)
    .filter((name) => !FAMILY_ORDER.includes(name))
    .sort()
    .map((name) => entries[name]);
  return [...ordered, ...remaining];
}

function classifyFamily(family, readinessPayload) {
  const reason = String(family?.reason || "");
  if (family?.family === "tts" && family?.runtime && String(family?.device || "").toLowerCase() === "cpu") {
    return "ready";
  }
  if (!family?.ready && isOllamaLocalRuntimeFallback(family, readinessPayload?.active_llm_runtime)) {
    return "degraded";
  }
  if (!family?.ready && FAILED_REASON_TOKENS.some((token) => reason.includes(token))) {
    return "failed";
  }
  return family?.ready ? "ready" : "degraded";
}

function familyDetail(family, state) {
  return `${state}: ${family.reason || "no readiness reason supplied"}`;
}

function appendFamilyRow(family, listEl, readinessPayload) {
  const item = document.createElement("li");
  const state = classifyFamily(family, readinessPayload);
  item.className = `family readiness-family ${state}`;
  item.dataset.family = family.family || "unknown";
  item.dataset.readinessState = state;
  item.title = familyDetail(family, state);

  const title = document.createElement("strong");
  title.textContent = FAMILY_LABELS[family.family] || String(family.family || "Unknown").toUpperCase();

  const runtime = document.createElement("span");
  runtime.textContent = `${family.runtime || "unknown-runtime"} / ${family.device || "unknown-device"}`;

  item.append(title, runtime);
  listEl.appendChild(item);
}

function appendPttRow(listEl) {
  appendFamilyRow(
    {
      family: "ptt",
      runtime: "desktop",
      device: "microphone",
      ready: true,
      reason: "Manual push-to-talk capture is available from the desktop voice controls.",
    },
    listEl,
    {},
  );
}

function readinessRows(families) {
  const rows = orderedFamilies(families);
  const ptt = {
    family: "ptt",
    runtime: "desktop",
    device: "microphone",
    ready: true,
    reason: "Manual push-to-talk capture is available from the desktop voice controls.",
  };
  const llmIndex = rows.findIndex((family) => family?.family === "llm");
  rows.splice(llmIndex >= 0 ? llmIndex + 1 : 0, 0, ptt);
  return rows;
}

export function renderReadiness(readinessPayload, containerEl) {
  if (!containerEl) return;

  containerEl.replaceChildren();
  containerEl.classList.remove("empty");

  if (!readinessPayload || typeof readinessPayload !== "object") {
    containerEl.textContent = "Readiness payload unavailable.";
    containerEl.classList.add("empty");
    return;
  }

  appendFactList(readinessPayload, containerEl);

  const list = document.createElement("ul");
  list.className = "families readiness-family-list";
  for (const family of readinessRows(readinessPayload.families)) {
    appendFamilyRow(family, list, readinessPayload);
  }
  containerEl.appendChild(list);
}
