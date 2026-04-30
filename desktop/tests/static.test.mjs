import { readFileSync } from "node:fs";
import { strict as assert } from "node:assert";

const main = readFileSync(new URL("../src/main.js", import.meta.url), "utf8");
const backend = readFileSync(new URL("../src-tauri/src/backend.rs", import.meta.url), "utf8");
const lib = readFileSync(new URL("../src-tauri/src/lib.rs", import.meta.url), "utf8");
const index = readFileSync(new URL("../src/index.html", import.meta.url), "utf8");

for (const token of ["RIFF", "WAVE", "fmt ", "data"]) {
  assert.ok(main.includes(token), `missing WAV token ${token}`);
}

assert.ok(main.includes("getUserMedia"), "PTT must request microphone capture");
assert.ok(main.includes("MediaRecorder"), "PTT must record microphone audio");
assert.ok(backend.includes("/task/voice"), "backend bridge must call /task/voice");
assert.ok(backend.includes("application/octet-stream"), "voice upload must be raw bytes");
assert.ok(!backend.toLowerCase().includes("multipart"), "voice upload must not use multipart");
assert.ok(!main.toLowerCase().includes("websocket"), "desktop must not use WebSockets");
assert.ok(backend.includes("/session/status"), "backend bridge must call /session/status");
assert.ok(lib.includes("get_session_status"), "Tauri command must expose get_session_status");
assert.ok(main.includes('invoke("get_session_status")'), "desktop must invoke get_session_status");
assert.ok(index.includes("session-turn-count"), "desktop must display session turn count");
assert.ok(backend.includes("/status/wake"), "backend bridge must call /status/wake");
assert.ok(lib.includes("get_wake_status"), "Tauri command must expose get_wake_status");
assert.ok(main.includes('invoke("get_wake_status")'), "desktop must invoke get_wake_status");
assert.ok(main.includes("PTT-only fallback"), "desktop must display PTT-only fallback state");
assert.ok(index.includes("wake-status"), "desktop must display wake status");
assert.ok(index.includes("wake-detail"), "desktop must display wake detail");
assert.ok(backend.includes("/personality/list"), "backend bridge must call /personality/list");
assert.ok(backend.includes("/personality/select"), "backend bridge must call /personality/select");
assert.ok(lib.includes("get_personality_list"), "Tauri command must expose get_personality_list");
assert.ok(lib.includes("select_personality"), "Tauri command must expose select_personality");
assert.ok(main.includes('invoke("get_personality_list")'), "desktop must invoke get_personality_list");
assert.ok(main.includes('invoke("select_personality"'), "desktop must invoke select_personality");
assert.ok(index.includes("personality-select"), "desktop must display personality selector");
assert.ok(index.includes("personality-current"), "desktop must display active personality");
assert.ok(main.includes("appendPresence"), "desktop must append UI-only presence messages");
assert.ok(main.includes("presenceByProfile"), "desktop must map profile-specific presence messages");

console.log("desktop static voice checks passed");