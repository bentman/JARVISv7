import { test } from "node:test";
import { strict as assert } from "node:assert";
import { bootDesktop, desktopResponses } from "./support.mjs";

const text = (app, selector) => app.$(selector)?.textContent ?? "";
const optionValues = (select) => [...select.options].map((option) => option.value);

async function started(options) {
  const app = await bootDesktop(options);
  await app.until(() => text(app, "#backend-health") === "ok" && !app.$("#send-button").disabled, "desktop startup");
  return app;
}

test("startup must render backend readiness, session, personality, and voice controls from the backend", async () => {
  const session = { session_id: "session-1", state: "LISTENING", turn_count: 0, active: true };
  const app = await started({
    responses: {
      get_session_status: session,
      get_desktop_status: () => ({ session, resident_voice: desktopResponses().get_resident_voice_status, wake: desktopResponses().get_wake_status }),
      get_personality_list: {
        active_profile_id: "default",
        profiles: [
          { profile_id: "default", display_name: "JARVIS", locale: "en", description: "Balanced assistant." },
          { profile_id: "concise", display_name: "Concise", locale: "en", description: "Short answers." },
        ],
        profile_errors: [{ profile_path: "config/personality/broken.yaml", reason: "missing locale" }],
      },
    },
  });
  try {
    assert.equal(text(app, "#session-id"), "session-1");
    assert.equal(text(app, "#session-turn-count"), "0");
    assert.equal(text(app, "#startup-state"), "Ready", "System State must come from readiness");
    const readiness = text(app, "#readiness-panel");
    for (const fact of ["Arch", "amd64", "Profile", "profile-1", "LLM"]) assert.ok(readiness.includes(fact), `readiness must show ${fact}`);
    assert.ok(!readiness.includes("Status"), "readiness must not repeat the status fact");
    assert.equal(app.$("#degraded-conditions").hidden, true, "a ready host must not show degraded rows");
    await app.until(() => app.commands().includes("get_desktop_status"), "the consolidated status poll");
    assert.ok(text(app, "#voice-detail").includes("state: LISTENING"), "conversation debug must render from session status");
    const activeRail = [...app.document.querySelectorAll(".turn-status-label.active")].map((node) => node.dataset.label);
    assert.deepEqual(activeRail, ["LISTEN"], "the turn rail must follow the backend session state");

    assert.deepEqual(optionValues(app.$("#personality-select")), ["default", "concise"]);
    assert.equal(text(app, "#personality-current"), "default");
    const detail = text(app, "#personality-detail");
    assert.ok(detail.includes("Locale: en") && detail.includes("Description: Balanced assistant."));
    assert.ok(detail.includes("Profile diagnostics") && detail.includes("config/personality/broken.yaml: missing locale"),
      "skipped personality profiles must be reported");

    assert.deepEqual(optionValues(app.$("#resident-tts-voice")), ["bf_isabella", "am_adam"], "voices must come from the backend");
    assert.equal(app.$("#resident-tts-voice").value, "bf_isabella");
    assert.equal(text(app, "#resident-tts-voice-hint"), "Selected voice is saved locally and applies to runtime.");
    assert.deepEqual(optionValues(app.$("#resident-mode")), ["ptt-only", "ptt+wake", "hands-free", "continuous"]);

    const log = [...app.document.querySelectorAll("#conversation-log .message.system p")].map((node) => node.textContent);
    assert.deepEqual(log, ["Backend started and readiness loaded.", "Active personality confirmed: default."]);

    const commands = app.commands();
    assert.ok(commands.indexOf("get_resident_voice_status") < commands.indexOf("get_readiness"),
      "the resident stream must be ensured before readiness is read");
    assert.ok(!commands.includes("start_wake_monitor"), "startup must not start wake monitoring on its own");
  } finally {
    app.close();
  }
});

test("a blocked readiness family must make System State Degraded and list why", async () => {
  const app = await started({
    responses: {
      get_readiness: {
        status: "ready", arch: "amd64", profile_id: "profile-1",
        families: { stt: { family: "stt", ready: false, reason: "STT model missing" }, llm: { family: "llm", ready: true } },
        services: {},
      },
    },
  });
  try {
    assert.equal(text(app, "#startup-state"), "Degraded");
    assert.equal(app.$("#degraded-conditions").hidden, false);
    assert.ok(text(app, "#degraded-conditions").includes("STT model missing"));
  } finally {
    app.close();
  }
});

test("a failed backend start must show its diagnostics and Backend unavailable", async () => {
  const failure = { failure: "backend exited", diagnostics: { python_path: "C:\\py\\python.exe", host: "127.0.0.1", port: 8765 } };
  const app = await bootDesktop({ responses: { start_backend: new Error(JSON.stringify(failure)) } });
  try {
    await app.until(() => text(app, "#backend-health") === "error", "the startup failure");
    assert.equal(text(app, "#startup-state"), "Backend unavailable");
    assert.equal(text(app, "#error-panel"), "backend exited");
    assert.ok(text(app, "#backend-diagnostics").includes("python_path: C:\\py\\python.exe"), "launch diagnostics must render");
    assert.equal(app.$("#send-button").disabled, true, "text entry must stay disabled without a backend");
  } finally {
    app.close();
  }

  const bridgeless = await bootDesktop({ bridge: false });
  try {
    await bridgeless.until(() => text(bridgeless, "#backend-health") === "error", "the missing bridge");
    assert.equal(text(bridgeless, "#startup-state"), "Backend unavailable");
    assert.match(text(bridgeless, "#error-panel"), /Tauri command bridge is unavailable/);
  } finally {
    bridgeless.close();
  }
});

test("a text turn must render as text with its profile metadata, and a failed turn must not fail System State", async () => {
  let reply = { final_state: "IDLE", response_text: "<b>Hello</b>", active_personality_profile_id: "default", profile_epoch: 2 };
  const app = await started({ responses: { submit_text: () => reply } });
  try {
    const submit = async (words) => {
      const turnsBefore = app.commands().filter((command) => command === "submit_text").length;
      app.$("#text-input").value = words;
      app.$("#text-form").dispatchEvent(new app.window.Event("submit", { cancelable: true }));
      await app.until(
        () => app.commands().filter((command) => command === "submit_text").length > turnsBefore && !app.$("#send-button").disabled,
        "the turn to finish",
      );
    };
    const sessionReads = () => app.commands().filter((command) => command === "get_session_status").length;
    const sessionReadsBefore = sessionReads();
    await submit("hi there");
    await app.until(() => sessionReads() > sessionReadsBefore, "the session refresh after a turn");
    assert.deepEqual(app.calls.find((call) => call.command === "submit_text").args, { text: "hi there" });
    const assistant = [...app.document.querySelectorAll("#conversation-log .message.assistant")].at(-1);
    assert.equal(assistant.querySelector("p").textContent, "<b>Hello</b>", "backend text must render as text, not markup");
    assert.equal(assistant.querySelector("b"), null);
    assert.equal(assistant.dataset.profileId, "default", "turn profile metadata belongs in the dataset");
    assert.ok(!assistant.textContent.includes("[profile:"), "profile metadata must not be appended to the reply");
    const presence = [...app.document.querySelectorAll("#conversation-log .message.presence p")].map((node) => node.textContent);
    assert.deepEqual(presence, ["Understood."], "the default profile's reasoning presence must be shown");

    reply = { final_state: "FAILED", failure_reason: "model timed out", response_text: "" };
    await submit("again");
    await app.until(() => text(app, "#error-panel") === "model timed out", "the turn failure");
    assert.equal(text(app, "#startup-state"), "Ready", "a failed turn must not replace System State");
  } finally {
    app.close();
  }
});

test("switching personality must apply through the backend, persist, and hold sends until confirmed", async () => {
  let confirmSelection;
  const app = await started({
    responses: {
      select_personality: (args) => new Promise((resolve) => {
        confirmSelection = () => resolve({ active: { profile_id: args.profileId, locale: "en", description: "Short answers." } });
      }),
    },
  });
  try {
    const select = app.$("#personality-select");
    select.value = "concise";
    select.dispatchEvent(new app.window.Event("change"));
    await app.until(() => typeof confirmSelection === "function", "the selection request");
    assert.equal(app.$("#text-input").disabled, true, "text entry must wait for the backend to confirm the profile");

    confirmSelection();
    await app.until(() => !app.$("#text-input").disabled, "the confirmed selection");
    assert.deepEqual(app.calls.find((call) => call.command === "select_personality").args, { profileId: "concise" });
    assert.equal(text(app, "#personality-current"), "concise");
    assert.equal(app.window.localStorage.getItem("jarvisv7_active_personality"), "concise");
    const system = [...app.document.querySelectorAll("#conversation-log .message.system p")].map((node) => node.textContent);
    assert.ok(system.some((line) => line.startsWith("Personality switched to concise")));
  } finally {
    app.close();
  }
});

test("saved preferences must be restored only when the backend still offers them", async () => {
  const restored = await started({
    storage: { jarvisv7_active_personality: "concise", jarvisv7_active_tts_voice: "am_adam" },
  });
  try {
    assert.deepEqual(restored.calls.find((call) => call.command === "select_personality")?.args, { profileId: "concise" });
    assert.deepEqual(restored.calls.find((call) => call.command === "set_resident_voice_tts_voice")?.args, { voice: "am_adam" });
    assert.equal(restored.$("#resident-tts-voice").value, "am_adam");
  } finally {
    restored.close();
  }

  const stale = await started({ storage: { jarvisv7_active_personality: "retired", jarvisv7_active_tts_voice: "gone_voice" } });
  try {
    assert.ok(!stale.commands().includes("select_personality"), "an unknown saved personality must not be applied");
    assert.ok(!stale.commands().includes("set_resident_voice_tts_voice"));
    assert.equal(stale.window.localStorage.getItem("jarvisv7_active_tts_voice"), null, "an unsupported saved voice must be cleared");
  } finally {
    stale.close();
  }
});

test("choosing a voice mode must go through the backend, and a wake outage must fall back to PTT", async () => {
  const app = await started({ responses: { get_wake_status: new Error("wake service down") } });
  try {
    const mode = app.$("#resident-mode");
    mode.value = "hands-free";
    mode.dispatchEvent(new app.window.Event("change"));
    await app.until(() => app.window.localStorage.getItem("jarvisv7_active_resident_voice_mode") === "hands-free", "the saved mode");
    assert.deepEqual(app.calls.find((call) => call.command === "set_resident_voice_mode")?.args, { mode: "hands-free" });
    await app.until(() => text(app, "#wake-indicator").includes("PTT-only fallback"), "the wake fallback");
    assert.equal(app.$("#wake-toggle").disabled, true);
  } finally {
    app.close();
  }
});

test("Advanced Controls must open one dialog, switch categories through the rail, and close from the backdrop", async () => {
  const app = await started();
  try {
    const dialog = app.$("#advanced-panel");
    const selected = () => [...app.document.querySelectorAll("#advanced-panel-rail button[data-category]")]
      .filter((button) => button.getAttribute("aria-selected") === "true").map((button) => button.dataset.category);
    assert.equal(dialog.parentElement, app.document.body, "the dialog must sit outside the main shell");

    app.$("#advanced-controls-trigger").click();
    assert.equal(dialog.open, true);
    await app.until(() => selected().join() === "providers", "the providers category");
    assert.ok(app.commands().includes("get_llm_config"), "Providers & Models must mount from the backend config");
    assert.equal(app.$("#providers-panel").hidden, false);

    app.document.querySelector('#advanced-panel-rail button[data-category="agents"]').click();
    await app.until(() => selected().join() === "agents", "the agents category");
    assert.ok(app.commands().includes("list_agents"), "the Agents category must mount");
    assert.equal(app.$("#providers-panel").hidden, true, "switching must close the previous category");

    dialog.dispatchEvent(new app.window.MouseEvent("click", { bubbles: true }));
    assert.equal(dialog.open, false, "a backdrop click must close the dialog");
    assert.deepEqual(selected(), [], "closing must clear the rail selection");
    assert.equal(app.$("#agents-panel").hidden, true, "closing must unmount the active category");

    app.$("#advanced-controls-trigger").click();
    await app.until(() => selected().join() === "agents", "reopening on the last category");
    app.$("#advanced-panel-close").click();
    assert.equal(dialog.open, false, "the Close control must close the dialog");
  } finally {
    app.close();
  }
});
