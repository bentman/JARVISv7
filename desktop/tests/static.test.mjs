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

console.log("desktop static voice checks passed");