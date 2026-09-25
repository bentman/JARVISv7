import { test } from "node:test";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { createApiClient } from "../src/api-client.js";
import { restartScopeDisables } from "../src/components/settings-panel.js";
import { main, apiClient, settingsPanel, llmProviderSettings, memoryPanel, actionsPanel, extensionsPanel, agentsPanel, backend, lib, index, style, cargoToml, tauriConfig, desktopSource } from "./support.mjs";

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
});

test("desktop PTT must not capture WebView microphone audio", async () => {
  assert.ok(!main.includes("getUserMedia"), "desktop PTT must not capture WebView microphone audio");
  assert.ok(!main.includes("MediaRecorder"), "desktop PTT must not record WebView microphone audio");
  assert.ok(backend.includes("/session/ptt"), "backend bridge must call resident /session/ptt");
  assert.ok(!backend.includes("application/octet-stream"), "desktop voice must not use raw upload bytes");
  assert.ok(!backend.toLowerCase().includes("multipart"), "voice upload must not use multipart");
  assert.ok(!main.toLowerCase().includes("websocket"), "desktop must not use WebSockets");
  assert.ok(backend.includes("python_path_for_host"), "desktop launcher must resolve its interpreter through the platform helper");
  assert.ok(backend.includes("/session/status"), "backend bridge must call /session/status");
  assert.ok(backend.includes("/status/desktop"), "backend bridge must call the consolidated desktop status endpoint");
  assert.ok(lib.includes("http_client: Client"), "desktop state must own one shared HTTP client");
  assert.ok(!backend.includes("Client::new()"), "backend requests must reuse the shared HTTP client");
  assert.ok(backend.includes("timeout(Duration::from_millis(700))"), "startup health probes must retain their request timeout");
  assert.ok(backend.includes("/status/wake"), "backend bridge must call /status/wake");
  assert.ok(backend.includes("/status/resident-voice"), "backend bridge must call /status/resident-voice");
  assert.ok(index.includes("Voice Selector"), "desktop must label resident voice selector");
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
  assert.ok(main.includes("advancedDialogEl.open"), "the restart badge must reflect whether the advanced surface is showing");
  assert.ok(index.includes("resident-voice-status"), "desktop must display resident voice diagnostics");
  assert.ok(index.includes("degraded-detail"), "desktop must include collapsed degraded detail surface");
  assert.ok(index.includes("Degraded list detail"), "desktop degraded detail surface must use the required title");
  assert.ok(index.includes("Conversation debug details"), "desktop must title the conversation debug surface correctly");
  assert.ok(index.includes("Backend diagnostics"), "desktop must include collapsed backend diagnostics surface");
  assert.ok(index.includes("backend-diagnostics"), "desktop must include backend diagnostics target element");
  assert.ok(index.indexOf("Conversation debug details") < index.indexOf("Backend diagnostics"), "backend diagnostics must follow conversation debug details");
  assert.ok(index.indexOf("Backend diagnostics") < index.indexOf("Degraded list detail"), "backend diagnostics must precede degraded list detail");
  assert.ok(main.includes("stopAllPolling()"), "desktop main must stop polling through helper");
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
  assert.ok(desktopSource.includes("barge-in"), "desktop must render resident barge-in status");
  assert.ok(desktopSource.includes("barge-in-wired"), "desktop must render resident barge-in wiring status");
  assert.ok(desktopSource.includes("follow-up-listening"), "desktop must render resident follow-up listening status");
  assert.ok(desktopSource.includes("continuous-active"), "desktop must render resident continuous active status");
  const settingsRestartPath = main.slice(main.indexOf("async function restartBackendForSettings"), main.indexOf("function updateSettingsRestartRequired"));
  assert.ok(settingsRestartPath.includes("ttsVoicePreferenceRestored = false"), "desktop settings restart must reset TTS voice restore guard");
  assert.ok(
    settingsRestartPath.indexOf("ttsVoicePreferenceRestored = false") < settingsRestartPath.indexOf("await completeBackendStart(startPayload)"),
    "desktop settings restart must reset TTS voice guard before backend-start postlude",
  );
  assert.ok(desktopSource.includes("status.stream"), "desktop must read backend resident stream object");
  assert.ok(desktopSource.includes("stream_present"), "desktop must keep flat resident stream fallback fields");
  assert.ok(desktopSource.includes("degraded_reasons"), "desktop must render resident degraded reasons");
  assert.ok(backend.includes("/personality/list"), "backend bridge must call /personality/list");
  assert.ok(backend.includes("/personality/select"), "backend bridge must call /personality/select");
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
