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

// Backend responses shaped like the Tauri bridge returns them; a test overrides only what it exercises.
export function desktopResponses() {
  const residentVoice = {
    mode: "ptt+wake", available: true, vad_configured: true, barge_in_supported: true, barge_in_wired: true,
    degraded_reasons: [], stream: { present: true, running: true, subscribers: 1, buffer_chunks: 0, dropped_chunks: 0, last_error: null },
    tts_voice: "bf_isabella", tts_supported_voices: ["bf_isabella", "am_adam"], tts_voice_restart_required: false,
  };
  const session = { session_id: "session-1", state: "IDLE", turn_count: 0, active: true };
  const wake = { provider: "openwakeword", available: true, monitoring: false, active: false, enabled: true, reason: "" };
  return {
    start_backend: { session_id: "session-1", turn_count: 0, diagnostics: {} },
    stop_backend: "",
    get_resident_voice_status: residentVoice,
    start_resident_voice_stream: residentVoice,
    set_resident_voice_mode: (args) => Object.assign(residentVoice, { mode: args.mode }),
    set_resident_voice_tts_voice: (args) => Object.assign(residentVoice, { tts_voice: args.voice }),
    get_readiness: {
      status: "ready", arch: "amd64", profile_id: "profile-1", active_llm_runtime: "llama.cpp",
      families: { stt: { family: "stt", ready: true }, tts: { family: "tts", ready: true }, llm: { family: "llm", ready: true } },
      services: {},
    },
    get_personality_list: {
      active_profile_id: "default",
      profiles: [
        { profile_id: "default", display_name: "JARVIS", locale: "en", description: "Balanced assistant." },
        { profile_id: "concise", display_name: "Concise", locale: "en", description: "Short answers." },
      ],
      profile_errors: [],
    },
    select_personality: (args) => ({ active: { profile_id: args.profileId, locale: "en", description: "Short answers." } }),
    get_session_status: session,
    get_desktop_status: { session, resident_voice: residentVoice, wake },
    get_wake_status: wake,
    start_wake_monitor: { ...wake, monitoring: true, active: true },
    stop_wake_monitor: "",
    submit_text: { final_state: "IDLE", response_text: "Hello.", active_personality_profile_id: "default", profile_epoch: 1 },
    get_llm_config: { profiles: [], selection: {} },
    list_agents: { agents: [] },
    list_agent_runs: { records: [] },
    list_agent_tools: { tools: [] },
  };
}

let bootCount = 0;

// Boots the real index.html and main.js in jsdom; only the Tauri invoke bridge is stood in.
export async function bootDesktop({ responses = {}, storage = {}, bridge = true } = {}) {
  const { JSDOM } = await import("jsdom");
  const html = readFileSync(new URL("../src/index.html", import.meta.url), "utf8");
  const dom = new JSDOM(html, { url: "http://localhost/" });
  const { window } = dom;
  // jsdom has no modal dialog support; model the open state and close event the HTML spec defines.
  window.HTMLDialogElement.prototype.showModal = function showModal() { this.setAttribute("open", ""); };
  window.HTMLDialogElement.prototype.close = function close() {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new window.Event("close"));
  };
  for (const [key, value] of Object.entries(storage)) window.localStorage.setItem(key, value);

  const calls = [];
  const table = { ...desktopResponses(), ...responses };
  if (bridge) {
    window.__TAURI__ = {
      core: {
        invoke: async (command, args = {}) => {
          calls.push({ command, args });
          if (!(command in table)) throw new Error(`no bridge response for ${command}`);
          const entry = table[command];
          const value = typeof entry === "function" ? await entry(args) : entry;
          if (value instanceof Error) throw value;
          return typeof value === "string" ? value : JSON.stringify(value);
        },
      },
    };
  }

  const previous = { window: globalThis.window, document: globalThis.document };
  globalThis.window = window;
  globalThis.document = window.document;
  await import(new URL(`../src/main.js?boot=${++bootCount}`, import.meta.url));

  async function until(predicate, message) {
    for (let attempt = 0; attempt < 200; attempt += 1) {
      if (predicate()) return;
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    throw new Error(`timed out waiting for ${message}`);
  }

  return {
    window,
    document: window.document,
    calls,
    commands: () => calls.map((call) => call.command),
    $: (selector) => window.document.querySelector(selector),
    until,
    close() {
      window.close();
      globalThis.window = previous.window;
      globalThis.document = previous.document;
    },
  };
}
