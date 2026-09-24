import { readFileSync } from "node:fs";

export const main = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");
export const apiClient = readFileSync(new URL("../src/api-client.js", import.meta.url), "utf8");
export const residentVoice = readFileSync(new URL("../src/components/resident-voice.js", import.meta.url), "utf8");
export const conversationDebug = readFileSync(new URL("../src/components/conversation-debug.js", import.meta.url), "utf8");
export const backendDiagnostics = readFileSync(new URL("../src/components/backend-diagnostics.js", import.meta.url), "utf8");
export const desktopPolling = readFileSync(new URL("../src/components/desktop-polling.js", import.meta.url), "utf8");
export const degradedList = readFileSync(new URL("../src/components/degraded-list.js", import.meta.url), "utf8");
export const settingsPanel = readFileSync(new URL("../src/components/settings-panel.js", import.meta.url), "utf8");
export const llmProviderSettings = readFileSync(new URL("../src/components/llm-provider-settings.js", import.meta.url), "utf8");
export const memoryPanel = readFileSync(new URL("../src/components/memory-panel.js", import.meta.url), "utf8");
export const actionsPanel = readFileSync(new URL("../src/components/actions-panel.js", import.meta.url), "utf8");
export const extensionsPanel = readFileSync(new URL("../src/components/extensions-panel.js", import.meta.url), "utf8");
export const agentsPanel = readFileSync(new URL("../src/components/agents-panel.js", import.meta.url), "utf8");
export const backend = readFileSync(new URL("../src-tauri/src/backend.rs", import.meta.url), "utf8");
export const lib = readFileSync(new URL("../src-tauri/src/lib.rs", import.meta.url), "utf8");
export const index = readFileSync(new URL("../src/index.html", import.meta.url), "utf8");
export const style = readFileSync(new URL("../src/style.css", import.meta.url), "utf8");
export const cargoToml = readFileSync(new URL("../src-tauri/Cargo.toml", import.meta.url), "utf8");
export const tauriConfig = JSON.parse(readFileSync(new URL("../src-tauri/tauri.conf.json", import.meta.url), "utf8"));
export const desktopSource = main + apiClient + residentVoice;

export const agentProfile = {
  profile_id: "researcher",
  display_name: "Researcher",
  purpose: "Investigate a question",
  instructions: "Cite what you find.",
  invocation_modes: ["direct", "as_tool"],
  capability_ids: ["search-public-web"],
  memory_scope: "episodic",
  approval_class: "standard",
  cancellable: true,
};

export const agentRunRecord = {
  kind: "action_proposal",
  capability_id: "agent-invoke-researcher",
  proposal_id: "p-1",
  recorded_at: "2026-09-07T10:00:00+00:00",
  record: { proposal_id: "p-1", status: "awaiting_approval" },
};

export function createElement(tagName) {
  const element = {
    tagName,
    className: "",
    id: "",
    dataset: {},
    textContent: "",
    children: [],
    parentElement: null,
    listeners: {},
    addEventListener(name, callback) { this.listeners[name] = callback; },
    appendChild(child) {
      child.parentElement = this;
      this.children.push(child);
      return child;
    },
    append(...children) {
      for (const child of children) this.appendChild(child);
    },
    replaceChildren(...children) {
      this.children = [];
      for (const child of children) this.appendChild(child);
    },
    setAttribute(name, value) { this[name] = value; },
    scrollTop: 0,
    focus() { this.focused = true; if (globalThis.document) globalThis.document.activeElement = this; },
    querySelector(selector) {
      if (selector === "#startup-state") return findElement(this, (node) => node.id === "startup-state");
      if (selector === ".label") return findElement(this, (node) => String(node.className).split(" ").includes("label"));
      if (selector === "strong") return findElement(this, (node) => node.tagName === "strong");
      return null;
    },
    querySelectorAll(selector) {
      if (selector === ".turn-status-label") {
        return findElements(this, (node) => String(node.className).split(" ").includes("turn-status-label"));
      }
      const dataAttr = /^\[data-([\w-]+)\]$/.exec(selector);
      if (dataAttr) {
        const key = dataAttr[1].replace(/-([a-z])/g, (_, letter) => letter.toUpperCase());
        return findElements(this, (node) => node.dataset && Object.prototype.hasOwnProperty.call(node.dataset, key));
      }
      return [];
    },
  };
  Object.defineProperty(element, "childNodes", { get() { return this.children; } });
  element.classList = {
    add(className) { this.toggle(className, true); },
    remove(className) { this.toggle(className, false); },
    toggle(className, enabled) {
      const classes = new Set(String(element.className).split(" ").filter(Boolean));
      if (enabled) classes.add(className);
      else classes.delete(className);
      element.className = [...classes].join(" ");
    },
  };
  return element;
}

export function findElement(node, predicate) {
  if (predicate(node)) return node;
  for (const child of node.children || []) {
    const found = findElement(child, predicate);
    if (found) return found;
  }
  return null;
}

export function findElements(node, predicate, found = []) {
  if (predicate(node)) found.push(node);
  for (const child of node.children || []) findElements(child, predicate, found);
  return found;
}

export function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

export function memoryRecord(overrides = {}) {
  return {
    fact_id: "memory-1",
    revision: 1,
    text: "The user prefers concise answers.",
    value: "concise",
    lifecycle_state: "pending_review",
    ...overrides,
  };
}

export function memoryDetail(record = memoryRecord()) {
  return {
    record,
    evidence: [],
    events: [],
    evidence_total: 0,
    evidence_returned: 0,
    events_total: 0,
    events_returned: 0,
  };
}
