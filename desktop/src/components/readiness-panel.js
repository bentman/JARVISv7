const FAMILY_ORDER = ["stt", "tts", "llm", "wake"];

const FAMILY_LABELS = {
  stt: "STT",
  tts: "TTS",
  llm: "LLM",
  wake: "Wake",
};

const FAILED_REASON_TOKENS = ["MISSING", "unavailable"];

function appendFactList(payload, containerEl) {
  const facts = document.createElement("dl");
  facts.className = "facts readiness-summary";

  for (const [label, value] of [
    ["Arch", payload?.arch],
    ["Profile", payload?.profile_id],
    ["Personality", payload?.active_personality_profile_id],
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

function classifyFamily(family) {
  const reason = String(family?.reason || "");
  if (!family?.ready && FAILED_REASON_TOKENS.some((token) => reason.includes(token))) {
    return "failed";
  }
  return family?.ready ? "ready" : "degraded";
}

function appendFamilyRow(family, listEl) {
  const item = document.createElement("li");
  const state = classifyFamily(family);
  item.className = `family readiness-family ${state}`;
  item.dataset.family = family.family || "unknown";
  item.dataset.readinessState = state;

  const title = document.createElement("strong");
  title.textContent = FAMILY_LABELS[family.family] || String(family.family || "Unknown").toUpperCase();

  const runtime = document.createElement("span");
  runtime.textContent = `${family.runtime || "unknown-runtime"} / ${family.device || "unknown-device"}`;

  const reason = document.createElement("small");
  reason.textContent = `${state}: ${family.reason || "no readiness reason supplied"}`;

  item.append(title, runtime, reason);
  listEl.appendChild(item);
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
  for (const family of orderedFamilies(readinessPayload.families)) {
    appendFamilyRow(family, list);
  }
  containerEl.appendChild(list);
}