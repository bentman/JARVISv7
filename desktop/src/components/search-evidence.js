export function renderSearchEvidence(container, evidence, openSource, onError) {
  if (!evidence || !Array.isArray(evidence.sources)) return;
  const sources = document.createElement("div");
  sources.className = "search-sources";
  for (const source of evidence.sources) {
    let url;
    try {
      url = new URL(source.url);
    } catch {
      continue;
    }
    if (!["http:", "https:"].includes(url.protocol) || url.username || url.password) continue;
    const link = document.createElement("a");
    link.href = url.href;
    link.textContent = `[${source.id}] ${source.title || url.hostname}`;
    link.title = `${source.basis === "page_excerpt" ? "Page excerpt" : "Search excerpt"} · ${source.retrieved_at || ""}`;
    link.addEventListener("click", (event) => {
      event.preventDefault();
      Promise.resolve(openSource(url.href)).catch(onError);
    });
    sources.appendChild(link);
  }
  if (evidence.limitations?.length) {
    const note = document.createElement("p");
    note.textContent = evidence.limitations.join(" ");
    sources.appendChild(note);
  }
  container.appendChild(sources);
}

export function createSearchStatus({ label, stopButton, cancelSearch, onError }) {
  let active = null;
  const requested = new Set();
  stopButton.addEventListener("click", async () => {
    if (!active) return;
    const target = active;
    const key = `${target.session_id}:${target.turn_id}`;
    requested.add(key);
    stopButton.disabled = true;
    label.textContent = "Stopping search…";
    try {
      await cancelSearch(target.session_id, target.turn_id);
    } catch (error) {
      requested.delete(key);
      if (active === target) stopButton.disabled = false;
      onError(error);
    }
  });
  return {
    render(evidence) {
      active = evidence && !["complete", "cancelled"].includes(evidence.stage) ? evidence : null;
      stopButton.hidden = !active;
      if (!active) {
        requested.clear();
        label.textContent = "";
        return;
      }
      const stopping = active.cancel_requested || requested.has(`${active.session_id}:${active.turn_id}`);
      stopButton.disabled = stopping;
      const stages = { planning: "Preparing search", searching: "Searching", reading: "Reading sources", synthesizing: "Preparing answer" };
      const attempts = (active.attempts || []).map((item) => `${item.provider}: ${item.status}`).join("; ");
      label.textContent = stopping ? "Stopping search…" : [stages[active.stage] || "Preparing answer", active.current_provider, attempts].filter(Boolean).join(" · ");
    },
  };
}
