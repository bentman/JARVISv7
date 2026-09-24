import { test } from "node:test";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { createApiClient } from "../src/api-client.js";
import { renderConversationDebug } from "../src/components/conversation-debug.js";
import { renderBackendDiagnostics } from "../src/components/backend-diagnostics.js";
import { createDesktopPolling } from "../src/components/desktop-polling.js";
import { restartScopeDisables } from "../src/components/settings-panel.js";
import { main, apiClient, residentVoice, conversationDebug, backendDiagnostics, desktopPolling, degradedList, settingsPanel, llmProviderSettings, memoryPanel, actionsPanel, extensionsPanel, agentsPanel, backend, lib, index, style, cargoToml, tauriConfig, desktopSource } from "./support.mjs";

test("operator panels must render through DOM text APIs and the api client only", async () => {
  for (const [panel, source] of Object.entries({ agentsPanel, memoryPanel, actionsPanel, extensionsPanel, llmProviderSettings })) {
    for (const banned of ["innerHTML", "fetch(", "localStorage", "style.display"]) {
      assert.ok(!source.includes(banned), `${panel} must not use ${banned}`);
    }
  }
});

test("desktop shell files the harness does not load must exist", async () => {
  for (const relativePath of [
    "../package.json",
    "../src-tauri/build.rs",
    "../src-tauri/src/main.rs",
    "../src-tauri/icons/icon.png",
    "../src-tauri/icons/icon.ico",
  ]) {
    assert.ok(existsSync(new URL(relativePath, import.meta.url)), `required desktop file missing: ${relativePath}`);
  }
});

test("Tauri must enable tray-icon support", async () => {
  assert.deepEqual(tauriConfig.bundle.icon, ["icons/icon.png", "icons/icon.ico"]);
  assert.ok(cargoToml.includes("tray-icon"), "Tauri must enable tray-icon support");
  assert.ok(lib.includes("TrayIconBuilder"), "Tauri shell must build the tray icon");
  for (const label of ["Start Backend", "Stop Backend", "Show Window", "Quit"]) {
    assert.ok(lib.includes(label), `tray menu must include ${label}`);
  }
  assert.ok(backend.includes("run_backend.py"), "desktop must launch the backend entrypoint");
  assert.ok(!`${backend}\n${lib}`.includes("run_jarvis.py"), "desktop must not launch the proving-host entrypoint");
  assert.ok(backend.includes('join("cache")'), "desktop must read backend daemon metadata under cache/");
  assert.ok(backend.includes("/daemon/status"), "desktop must probe daemon status before spawning");
  assert.ok(backend.includes("/daemon/shutdown"), "desktop daemon stop must use the token-protected backend route");
  assert.ok(!backend.includes("netstat -ano"), "desktop must not discover unrelated port owners with netstat");
  assert.ok(!backend.includes("taskkill"), "desktop must not kill unrelated port owners");
});

test("desktop PTT must not capture WebView microphone audio", async () => {
  assert.ok(!main.includes("getUserMedia"), "desktop PTT must not capture WebView microphone audio");
  assert.ok(!main.includes("MediaRecorder"), "desktop PTT must not record WebView microphone audio");
  assert.ok(backend.includes("/session/ptt"), "backend bridge must call resident /session/ptt");
  assert.ok(!backend.includes("application/octet-stream"), "desktop voice must not use raw upload bytes");
  assert.ok(!backend.toLowerCase().includes("multipart"), "voice upload must not use multipart");
  assert.ok(!main.toLowerCase().includes("websocket"), "desktop must not use WebSockets");
  assert.ok(backend.includes("python_path_for_host"), "desktop launcher must resolve its interpreter through the platform helper");
  assert.ok(backend.includes('venv_root.join("Scripts").join("python.exe")'), "desktop launcher must preserve the Windows venv interpreter path");
  assert.ok(backend.includes('venv_root.join("bin").join("python")'), "desktop launcher must resolve the Linux venv interpreter path");
  assert.ok(backend.includes("/session/status"), "backend bridge must call /session/status");
  assert.ok(backend.includes("/status/desktop"), "backend bridge must call the consolidated desktop status endpoint");
  assert.ok(lib.includes("http_client: Client"), "desktop state must own one shared HTTP client");
  assert.ok(!backend.includes("Client::new()"), "backend requests must reuse the shared HTTP client");
  assert.ok(backend.includes("timeout(Duration::from_millis(700))"), "startup health probes must retain their request timeout");
  assert.ok(index.includes("session-turn-count"), "desktop must display session turn count");
  assert.ok(backend.includes("/status/wake"), "backend bridge must call /status/wake");
  assert.ok(backend.includes("/status/resident-voice"), "backend bridge must call /status/resident-voice");
  assert.ok(desktopSource.includes("PTT-only fallback"), "desktop must display PTT-only fallback state");
  assert.ok(index.includes("wake-indicator"), "desktop must display wake status");
  assert.ok(index.includes("wake-toggle"), "desktop must expose wake toggle");
  assert.ok(index.includes("resident-mode"), "desktop must expose resident voice mode control");
  assert.ok(index.includes("resident-tts-voice"), "desktop must expose resident voice selector");
  assert.ok(index.includes("Voice Selector"), "desktop must label resident voice selector");
  assert.ok(index.includes("ptt-only"), "desktop must include PTT-only resident mode");
  assert.ok(index.indexOf("resident-voice-panel") < index.indexOf("wake-monitor-panel"), "Resident Voice must render above Wake in the operator panel");
  assert.ok(
    index.indexOf("personality-panel") < index.indexOf("resident-voice-panel"),
    "Personality must render above Resident Voice in the operator panel",
  );
  assert.ok(
    index.indexOf("advanced-controls-trigger") < index.indexOf('class="panel conversation-panel"'),
    "the advanced-control launch button must sit in the left status sidebar below the status indicators",
  );
  assert.ok(
    index.indexOf("service-status") < index.indexOf("advanced-controls-trigger"),
    "Backend, Readiness and Services must stay above the advanced-control launch button",
  );
  assert.ok(index.includes('<dialog id="advanced-panel"'), "advanced controls must open one dialog surface");
  assert.ok(index.includes('id="advanced-panel-rail"'), "the advanced-control dialog must carry a category rail");
  assert.ok(index.includes('id="advanced-panel-close"'), "the advanced-control dialog must expose an explicit close control");
  for (const category of ["providers", "settings", "memory", "actions", "extensions", "agents"]) {
    assert.ok(
      index.includes(`data-category="${category}"`),
      `advanced-control rail missing category: ${category}`,
    );
    assert.ok(
      index.includes(`id="${category}-panel"`),
      `advanced-control detail pane missing mount: ${category}-panel`,
    );
  }
  for (const label of ["Providers &amp; Models", "Operator Settings", "Actions &amp; Capabilities", "Agents"]) {
    assert.ok(index.includes(label), `advanced-control rail missing label: ${label}`);
  }
  assert.ok(
    index.indexOf("<dialog") > index.indexOf("</main>"),
    "the advanced-control dialog must sit outside the overflow-hidden shell",
  );
  assert.ok(main.includes("showModal()"), "the advanced-control surface must use native modal dismissal and focus handling");
  assert.ok(
    main.includes('advancedDialogEl.addEventListener("close"'),
    "Escape, the close button and a backdrop click must all tear down through one close hook",
  );
  assert.ok(
    main.includes("event.target === advancedDialogEl"),
    "a backdrop click must dismiss the advanced-control surface",
  );
  assert.ok(main.includes("advancedDialogEl.open"), "the restart badge must reflect whether the advanced surface is showing");
  assert.ok(main.includes('aria-selected'), "the rail must mark the showing category");
  assert.ok(main.includes("createAgentsPanel"), "Agents must be mounted in the desktop surface");
  assert.ok(main.includes("openProviderSettings"), "Providers & Models must be mounted as its own category");
  assert.ok(index.includes("hands-free"), "desktop must include hands-free resident mode");
  assert.ok(index.includes("continuous"), "desktop must include continuous resident mode");
  assert.ok(index.includes("resident-voice-status"), "desktop must display resident voice diagnostics");
  assert.ok(index.includes("degraded-detail"), "desktop must include collapsed degraded detail surface");
  assert.ok(index.includes("Degraded list detail"), "desktop degraded detail surface must use the required title");
  assert.ok(index.includes("Conversation debug details"), "desktop must title the conversation debug surface correctly");
  assert.ok(index.includes("Backend diagnostics"), "desktop must include collapsed backend diagnostics surface");
  assert.ok(index.includes("backend-diagnostics"), "desktop must include backend diagnostics target element");
  assert.ok(index.indexOf("Conversation debug details") < index.indexOf("Backend diagnostics"), "backend diagnostics must follow conversation debug details");
  assert.ok(index.indexOf("Backend diagnostics") < index.indexOf("Degraded list detail"), "backend diagnostics must precede degraded list detail");
  assert.ok(main.includes("renderConversationDebug(status, voiceDetailEl)"), "desktop must render conversation debug from session status");
  assert.ok(main.includes("renderBackendDiagnostics"), "desktop must render backend diagnostics");
  assert.ok(main.includes("error.diagnostics"), "startup failures must not collapse only into String(error)");
  assert.ok(desktopPolling.includes("let pollTimer"), "desktop polling helper must own one consolidated timer handle");
  assert.ok(desktopPolling.includes("refreshDesktopStatus"), "slow polling ticks must use the consolidated desktop snapshot");
  for (const functionName of ["startAllPolling", "stopAllPolling"]) {
    assert.ok(desktopPolling.includes(functionName), `desktop polling helper must expose ${functionName}`);
  }
  assert.ok(main.includes('import { createDesktopPolling } from "./components/desktop-polling.js"'), "desktop main must import polling helper");
  assert.ok(main.includes("createDesktopPolling({"), "desktop main must create polling helper with refresh callbacks");
  assert.ok(main.includes("startAllPolling()"), "desktop main must start polling through helper");
  assert.ok(main.includes("stopAllPolling()"), "desktop main must stop polling through helper");
  for (const timerName of ["wakePollTimer", "sessionPollTimer", "residentVoicePollTimer"]) {
    assert.ok(!main.includes(timerName), `desktop main must not own ${timerName}`);
  }
  assert.ok(main.includes("async function completeBackendStart(startPayload)"), "desktop main must define shared backend-start postlude helper");
  assert.equal(
    [...main.matchAll(/await completeBackendStart\(startPayload\)/g)].length,
    2,
    "startDesktop and restartBackendForSettings must share backend-start postlude helper",
  );
  assert.ok(
    main.indexOf("async function completeBackendStart") < main.indexOf("async function startDesktop"),
    "backend-start postlude helper must be shared before startup functions use it",
  );
  assert.ok(lib.includes("startup_failure_payload"), "Tauri start_backend failures must return structured diagnostics");
  assert.ok(backend.includes("stdout_tail"), "backend diagnostics failure payload must include stdout tail");
  assert.ok(backend.includes("stderr_tail"), "backend diagnostics failure payload must include stderr tail");
  for (const token of ["python_path", "backend_script_path", "working_directory", "endpoint", "stdout_log", "stderr_log", "stdout_tail", "stderr_tail"]) {
    assert.ok(backendDiagnostics.includes(token), `backend diagnostics renderer must include ${token}`);
  }
  assert.ok(main.includes("await refreshSessionStatus()"), "desktop text and voice flows must refresh session status");
  assert.ok(conversationDebug.includes("latest_turn"), "conversation debug must render latest-turn session status");
  assert.ok(conversationDebug.includes("artifact_path"), "conversation debug must render turn artifact path");
  assert.ok(conversationDebug.includes("runtime_context"), "conversation debug must render runtime context");
  assert.ok(conversationDebug.includes("phase_durations_ms"), "conversation debug must render latest-turn phase timing");
  assert.ok(conversationDebug.includes("failure_phase"), "conversation debug must render failure phase");
  assert.ok(conversationDebug.includes("raw_audio_path"), "conversation debug must render raw audio replay path");
  assert.ok(conversationDebug.includes("degraded_reason"), "conversation debug must render compact degraded reason");
  assert.ok(!conversationDebug.includes("last_transcript"), "conversation debug must not duplicate transcript text");
  assert.ok(!conversationDebug.includes("last_response"), "conversation debug must not duplicate assistant response text");
  assert.ok(
    residentVoice.includes("latestTurn?.input_modality === \"voice\""),
    "resident voice completion de-dupe must not key stale voice fields from latest text turns",
  );
  assert.ok(main.includes("renderDegradedList(readiness, degradedEl)"), "desktop degraded detail must render from existing readiness payload");
  assert.ok(
    main.indexOf("await ensureResidentVoiceStream()") < main.indexOf("const readiness = await api.getReadiness()"),
    "desktop must fetch readiness after resident stream startup settles",
  );
  assert.ok(
    main.indexOf("async function completeBackendStart") < main.indexOf("const readiness = await api.getReadiness()"),
    "desktop backend-start postlude must own readiness fetch",
  );
  assert.ok(
    main.indexOf("await startWakeMonitorIfAvailable()") > main.indexOf("async function setResidentVoiceMode"),
    "desktop must start wake only through explicit resident mode selection",
  );
  assert.ok(
    !main
      .slice(main.indexOf("async function completeBackendStart"), main.indexOf("const readiness = await api.getReadiness()"))
      .includes("await startWakeMonitorIfAvailable()"),
    "desktop backend startup must not automatically start wake monitoring",
  );
  assert.ok(degradedList.includes("closest(\"details\")"), "degraded detail renderer must control its collapsed details container");
  assert.ok(degradedList.includes("optional-service"), "degraded detail must label optional services separately");
  assert.ok(desktopSource.includes("barge-in"), "desktop must render resident barge-in status");
  assert.ok(desktopSource.includes("barge-in-wired"), "desktop must render resident barge-in wiring status");
  assert.ok(desktopSource.includes("follow-up-listening"), "desktop must render resident follow-up listening status");
  assert.ok(desktopSource.includes("continuous-active"), "desktop must render resident continuous active status");
  assert.ok(residentVoice.includes("latestTurnIsVoice && latestTurn?.turn_id"), "resident voice completion dedupe must prefer voice latest-turn identity");
  assert.ok(conversationDebug.includes("currentFailureWithoutTurn"), "conversation debug must show current capture failures ahead of stale latest-turn data");
  assert.ok(main.includes("ensureResidentVoiceStream"), "desktop must start resident stream before resident wake/mode proof");
  assert.ok(main.includes("setResidentVoiceMode"), "desktop must call backend resident mode mutation");
  assert.ok(main.includes("setResidentTtsVoice"), "desktop must call backend resident TTS voice mutation");
  assert.ok(main.includes("renderResidentTtsVoiceSelector"), "desktop must render TTS voice options from backend status");
  assert.ok(main.includes("tts_supported_voices"), "desktop voice selector must use backend-supported voice options");
  assert.ok(main.includes("jarvisv7_active_tts_voice"), "desktop voice selector must persist the selected voice locally");
  assert.ok(main.includes("applyStoredTtsVoiceIfAvailable"), "desktop voice selector must restore a valid cached voice");
  assert.ok(main.includes("removeItem(TTS_VOICE_STORAGE_KEY"), "desktop voice selector must clear invalid cached voices");
  const settingsRestartPath = main.slice(main.indexOf("async function restartBackendForSettings"), main.indexOf("function updateSettingsRestartRequired"));
  assert.ok(settingsRestartPath.includes("ttsVoicePreferenceRestored = false"), "desktop settings restart must reset TTS voice restore guard");
  assert.ok(
    settingsRestartPath.indexOf("ttsVoicePreferenceRestored = false") < settingsRestartPath.indexOf("await completeBackendStart(startPayload)"),
    "desktop settings restart must reset TTS voice guard before backend-start postlude",
  );
  assert.ok(index.includes("Selected voice is saved locally and applies to runtime."), "desktop voice hint must describe local runtime persistence");
  assert.ok(desktopSource.includes("status.stream"), "desktop must read backend resident stream object");
  assert.ok(desktopSource.includes("stream_present"), "desktop must keep flat resident stream fallback fields");
  assert.ok(desktopSource.includes("degraded_reasons"), "desktop must render resident degraded reasons");
  assert.ok(backend.includes("/personality/list"), "backend bridge must call /personality/list");
  assert.ok(backend.includes("/personality/select"), "backend bridge must call /personality/select");
  assert.ok(index.includes("personality-select"), "desktop must display personality selector");
  assert.ok(index.includes("personality-current"), "desktop must display active personality");
  assert.ok(main.includes("profile_errors"), "desktop must render backend personality profile diagnostics");
  assert.ok(main.includes("Profile diagnostics"), "desktop must label skipped personality profile diagnostics");
  assert.ok(main.includes("personalitySelectionPending"), "desktop must guard sends while profile selection is pending");
  assert.ok(main.includes("Active personality confirmed"), "desktop must show backend-confirmed active personality");
  assert.ok(main.includes("active_personality_profile_id"), "desktop must render backend-reported turn profile metadata");
  assert.ok(main.includes("jarvisv7_active_personality"), "desktop must persist the backend-confirmed active personality");
  assert.ok(main.includes("dataset.profileId"), "desktop must attach turn profile metadata without appending it to assistant text");
  assert.ok(!main.includes("[profile:"), "desktop must not append profile metadata into assistant message text");
  assert.ok(main.includes("Description"), "desktop must display profile description");
  assert.ok(main.includes("Locale"), "desktop must display profile locale");
  assert.ok(main.includes("personalityDetailEl.textContent"), "desktop must keep compact personality metadata on one rendered line");
  assert.ok(main.includes("appendPresence"), "desktop must append UI-only presence messages");
  assert.ok(main.includes("presenceByProfile"), "desktop must map profile-specific presence messages");
  assert.ok(settingsPanel.includes("field.options"), "settings panel must render select controls from backend metadata");
  assert.ok(settingsPanel.includes("field.section"), "settings panel must group settings from backend metadata");
  assert.ok(settingsPanel.includes("field.advanced"), "settings panel must use advanced metadata from backend");
  assert.ok(!settingsPanel.includes("http://127.0.0.1:8765/config/operator"), "settings panel must not call backend URL directly");
  assert.ok(
    !settingsPanel.includes('querySelectorAll("input, select, button")'),
    "an operator-config save must not blanket-disable another category's controls",
  );
  assert.ok(!settingsPanel.includes("llm-provider-settings.js"), "Providers & Models must not be nested inside the operator settings form");
  assert.equal(restartScopeDisables(["operator"], "operator"), true);
  assert.equal(restartScopeDisables(["operator"], "provider"), false, "restart scopes must not leak across categories");
  assert.equal(restartScopeDisables(new Set(["provider"]), "provider"), true);
  assert.equal(restartScopeDisables(null, "operator"), false);
  assert.ok(llmProviderSettings.includes("Model Providers"), "settings must expose Model Providers");
  assert.ok(llmProviderSettings.includes("Allow cloud escalation"), "settings must expose cloud escalation authorization");
  assert.ok(llmProviderSettings.includes("Test connection"), "settings must expose provider readiness testing");
  assert.ok(llmProviderSettings.includes("Remove stored credential"), "settings must expose credential removal");
  assert.ok(llmProviderSettings.includes("openProviderSettings"), "Providers & Models must be mountable as its own advanced-control category");
});

test("every client command must be a registered Tauri command and every bridge call a backend route", async () => {
  const invoked = new Set([...apiClient.matchAll(/invoke(?:Memory)?\((?:invoke, )?"([a-z_]+)"/g)].map((m) => m[1]));
  const handlerStart = lib.indexOf("generate_handler![");
  const handlers = lib.slice(handlerStart, lib.indexOf("]", handlerStart));
  const registered = new Set([...handlers.matchAll(/([a-z_]+)\s*[,\n]/g)].map((m) => m[1]));
  assert.deepEqual([...invoked].filter((command) => !registered.has(command)), [], "the client must not invoke an unregistered command");
  assert.deepEqual([...registered].filter((command) => !invoked.has(command)), [], "every registered command must be used by the client");

  const normalize = (path) => path.split("?")[0].replace(/\{[^}]*\}/g, "{}").replace(/\/$/, "") || "/";
  const called = new Set([...backend.matchAll(/format!\(\s*"\{base_url\}(\/[^"]*)"/g)].map((m) => normalize(m[1])));
  for (const m of `${backend}\n${lib}`.matchAll(/\b(?:get_json|post_wake_action)\([^;]*?"(\/[^"]*)"/g)) called.add(normalize(m[1]));
  const routesDir = new URL("../../backend/app/api/routes/", import.meta.url);
  const routes = [];
  for (const file of readdirSync(routesDir).filter((name) => name.endsWith(".py"))) {
    const text = readFileSync(new URL(file, routesDir), "utf8");
    const prefix = text.match(/APIRouter\(prefix="([^"]*)"/)?.[1] ?? "";
    for (const m of text.matchAll(/@router\.(?:get|post|put|delete|patch)\(\s*"([^"]*)"/g)) routes.push(normalize(prefix + m[1]).split("/"));
  }
  // A trailing placeholder in a bridge path selects one of several backend actions (e.g. /memory/{fact_id}/{action}).
  const served = (path) => routes.some((route) => route.length === path.length
    && path.every((segment, i) => segment === route[i] || (segment === "{}" && i === path.length - 1)));
  assert.ok(called.size > 40, "the bridge route scan must find the bridge's backend calls");
  assert.deepEqual([...called].filter((path) => !served(path.split("/"))), [], "every bridge call must reach a backend route");
});

test("backend startup failures must reach the operator with their diagnostics", async () => {
  const structured = { failure: "backend exited", diagnostics: { python_path: "py", port: "8765" } };
  const failing = (message) => createApiClient(async () => { throw new Error(message); });

  const fromPayload = await failing(JSON.stringify(structured)).startBackend().catch((error) => error);
  assert.equal(fromPayload.message, "backend exited");
  assert.deepEqual(fromPayload.diagnostics, structured);

  const fromText = await failing("backend exited\npython=C:\\py\\python.exe\nscript=run_backend.py\nport=8765").startBackend().catch((error) => error);
  assert.equal(fromText.message, "backend exited");
  assert.deepEqual(fromText.diagnostics.diagnostics, {
    python_path: "C:\\py\\python.exe", backend_script_path: "run_backend.py", port: "8765",
  });
});
