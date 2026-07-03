import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";
import { collectDegradedConditions } from "../src/components/degraded-list.js";

const main = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");
const apiClient = readFileSync(new URL("../src/api-client.js", import.meta.url), "utf8");
const residentVoice = readFileSync(new URL("../src/components/resident-voice.js", import.meta.url), "utf8");
const degradedList = readFileSync(new URL("../src/components/degraded-list.js", import.meta.url), "utf8");
const settingsPanel = readFileSync(new URL("../src/components/settings-panel.js", import.meta.url), "utf8");
const backend = readFileSync(new URL("../src-tauri/src/backend.rs", import.meta.url), "utf8");
const lib = readFileSync(new URL("../src-tauri/src/lib.rs", import.meta.url), "utf8");
const index = readFileSync(new URL("../src/index.html", import.meta.url), "utf8");
const desktopSource = main + apiClient + residentVoice;

assert.ok(!main.includes("getUserMedia"), "desktop PTT must not capture WebView microphone audio");
assert.ok(!main.includes("MediaRecorder"), "desktop PTT must not record WebView microphone audio");
assert.ok(!backend.includes("/task/voice"), "backend bridge must not call legacy /task/voice");
assert.ok(backend.includes("/session/ptt"), "backend bridge must call resident /session/ptt");
assert.ok(lib.includes("invoke_resident_ptt"), "Tauri command must expose invoke_resident_ptt");
assert.ok(apiClient.includes('invoke("invoke_resident_ptt")'), "desktop API client must invoke resident PTT");
assert.ok(!backend.includes("application/octet-stream"), "desktop voice must not use raw upload bytes");
assert.ok(!backend.toLowerCase().includes("multipart"), "voice upload must not use multipart");
assert.ok(!main.toLowerCase().includes("websocket"), "desktop must not use WebSockets");
assert.ok(backend.includes("/session/status"), "backend bridge must call /session/status");
assert.ok(lib.includes("get_session_status"), "Tauri command must expose get_session_status");
assert.ok(apiClient.includes('invoke("get_session_status")'), "desktop API client must invoke get_session_status");
assert.ok(index.includes("session-turn-count"), "desktop must display session turn count");
assert.ok(backend.includes("/status/wake"), "backend bridge must call /status/wake");
assert.ok(backend.includes("/status/resident-voice"), "backend bridge must call /status/resident-voice");
assert.ok(lib.includes("get_wake_status"), "Tauri command must expose get_wake_status");
assert.ok(lib.includes("get_resident_voice_status"), "Tauri command must expose get_resident_voice_status");
assert.ok(lib.includes("start_resident_voice_stream"), "Tauri command must expose start_resident_voice_stream");
assert.ok(lib.includes("set_resident_voice_mode"), "Tauri command must expose set_resident_voice_mode");
assert.ok(apiClient.includes('invoke("get_wake_status")'), "desktop API client must invoke get_wake_status");
assert.ok(apiClient.includes('invoke("get_resident_voice_status")'), "desktop API client must invoke get_resident_voice_status");
assert.ok(apiClient.includes('invoke("start_resident_voice_stream")'), "desktop API client must invoke start_resident_voice_stream");
assert.ok(apiClient.includes('invoke("set_resident_voice_mode"'), "desktop API client must invoke set_resident_voice_mode");
assert.ok(desktopSource.includes("PTT-only fallback"), "desktop must display PTT-only fallback state");
assert.ok(index.includes("wake-indicator"), "desktop must display wake status");
assert.ok(index.includes("wake-toggle"), "desktop must expose wake toggle");
assert.ok(index.includes("resident-mode"), "desktop must expose resident voice mode control");
assert.ok(index.includes("ptt-only"), "desktop must include PTT-only resident mode");
assert.ok(index.includes("hands-free"), "desktop must include hands-free resident mode");
assert.ok(index.includes("continuous"), "desktop must include continuous resident mode");
assert.ok(index.includes("resident-voice-status"), "desktop must display resident voice diagnostics");
assert.ok(index.includes("degraded-detail"), "desktop must include collapsed degraded detail surface");
assert.ok(index.includes("Degraded list detail"), "desktop degraded detail surface must use the required title");
assert.ok(index.indexOf("Voice debug details") < index.indexOf("Degraded list detail"), "desktop degraded detail must be directly after voice debug details");
assert.ok(main.includes("renderDegradedList(readiness, degradedEl)"), "desktop degraded detail must render from existing readiness payload");
assert.ok(degradedList.includes("closest(\"details\")"), "degraded detail renderer must control its collapsed details container");
assert.ok(degradedList.includes("optional-service"), "degraded detail must label optional services separately");
assert.ok(desktopSource.includes("barge-in"), "desktop must render resident barge-in status");
assert.ok(desktopSource.includes("barge-in-wired"), "desktop must render resident barge-in wiring status");
assert.ok(desktopSource.includes("follow-up-listening"), "desktop must render resident follow-up listening status");
assert.ok(desktopSource.includes("continuous-active"), "desktop must render resident continuous active status");
assert.ok(main.includes("ensureResidentVoiceStream"), "desktop must start resident stream before resident wake/mode proof");
assert.ok(main.includes("setResidentVoiceMode"), "desktop must call backend resident mode mutation");
assert.ok(desktopSource.includes("status.stream"), "desktop must read backend resident stream object");
assert.ok(desktopSource.includes("stream_present"), "desktop must keep flat resident stream fallback fields");
assert.ok(desktopSource.includes("degraded_reasons"), "desktop must render resident degraded reasons");
assert.ok(backend.includes("/personality/list"), "backend bridge must call /personality/list");
assert.ok(backend.includes("/personality/select"), "backend bridge must call /personality/select");
assert.ok(lib.includes("get_personality_list"), "Tauri command must expose get_personality_list");
assert.ok(lib.includes("select_personality"), "Tauri command must expose select_personality");
assert.ok(apiClient.includes('invoke("get_personality_list")'), "desktop API client must invoke get_personality_list");
assert.ok(apiClient.includes('invoke("select_personality"'), "desktop API client must invoke select_personality");
assert.ok(index.includes("personality-select"), "desktop must display personality selector");
assert.ok(index.includes("personality-current"), "desktop must display active personality");
assert.ok(main.includes("appendPresence"), "desktop must append UI-only presence messages");
assert.ok(main.includes("presenceByProfile"), "desktop must map profile-specific presence messages");
assert.ok(settingsPanel.includes("field.options"), "settings panel must render select controls from backend metadata");
assert.ok(settingsPanel.includes("field.section"), "settings panel must group settings from backend metadata");
assert.ok(settingsPanel.includes("field.advanced"), "settings panel must use advanced metadata from backend");
assert.ok(!settingsPanel.includes("LLM_MODEL_MODE"), "settings panel must not hardcode model mode field");
assert.ok(!settingsPanel.includes("Local LLM intent (llama.cpp)"), "settings panel must not hardcode backend sections");
assert.ok(!settingsPanel.includes("http://127.0.0.1:8765/config/operator"), "settings panel must not call backend URL directly");

const readyConditions = collectDegradedConditions({
  status: "ready",
  active_llm_runtime: "llama.cpp",
  families: {
    llm: { family: "llm", ready: true, reason: "local llama.cpp available" },
    stt: { family: "stt", ready: true, reason: "stt ready" },
  },
  preflight: { probe_error_count: 0 },
  services: {
    redis: { reachable: true, reason: "reachable" },
    searxng: { reachable: true, reason: "container reachable; json usable" },
  },
  resident_audio: { degraded_reasons: [] },
});
assert.equal(readyConditions.length, 0, "ready desktop payload must not show degraded detail rows");

const degradedConditions = collectDegradedConditions({
  status: "degraded",
  active_llm_runtime: "ollama",
  families: {
    llm: { family: "llm", ready: true, reason: "test ollama available", degraded_reason: "Degraded-no-sidecar-binary" },
    stt: { family: "stt", ready: false, reason: "STT model missing" },
    tts: { family: "tts", ready: true, reason: "tts ready" },
  },
  preflight: { probe_error_count: 1 },
  services: {
    redis: { reachable: false, reason: "connection refused" },
  },
  resident_audio: { degraded_reasons: ["resident audio stream is stopped"] },
});
assert.deepEqual(
  degradedConditions.map((row) => row.kind),
  ["backend", "family", "family", "resident-audio", "optional-service"],
  "degraded detail must include selected-path blockers, resident audio reasons, and optional services separately",
);

console.log("desktop static voice checks passed");
