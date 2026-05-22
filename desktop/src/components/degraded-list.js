const FAMILY_ORDER = ["stt", "tts", "llm", "wake"];

const FAMILY_LABELS = {
  stt: "STT",
  tts: "TTS",
  llm: "LLM",
  wake: "Wake",
};

const FALLBACK_REASON_TOKENS = ["provider-override-missing"];

function orderedFamilies(families) {
  const entries = families || {};
  const ordered = FAMILY_ORDER.filter((name) => entries[name]).map((name) => entries[name]);
  const remaining = Object.keys(entries)
    .filter((name) => !FAMILY_ORDER.includes(name))
    .sort()
    .map((name) => entries[name]);
  return [...ordered, ...remaining];
}

function isDegradedCondition(family) {
  const reason = String(family?.reason || "");
  return !family?.ready || FALLBACK_REASON_TOKENS.some((token) => reason.includes(token));
}

export function renderDegradedList(readinessPayload, containerEl) {
  if (!containerEl) return;

  containerEl.replaceChildren();
  const affectedFamilies = orderedFamilies(readinessPayload?.families).filter(isDegradedCondition);

  if (affectedFamilies.length === 0) {
    containerEl.hidden = true;
    return;
  }

  containerEl.hidden = false;
  const heading = document.createElement("h3");
  heading.textContent = "Degraded conditions";

  const list = document.createElement("ul");
  list.className = "degraded-condition-list";

  for (const family of affectedFamilies) {
    const item = document.createElement("li");
    item.className = "degraded-condition";
    item.dataset.family = family.family || "unknown";

    const label = document.createElement("strong");
    label.textContent = FAMILY_LABELS[family.family] || String(family.family || "Unknown").toUpperCase();

    const reason = document.createElement("span");
    reason.textContent = family.reason || "no readiness reason supplied";

    item.append(label, reason);
    list.appendChild(item);
  }

  containerEl.append(heading, list);
}