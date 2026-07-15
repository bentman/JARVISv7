const ACTIVE_SESSION_INTERVAL_MS = 100;
const IDLE_SESSION_INTERVAL_MS = 2000;
const STATUS_INTERVAL_MS = 3000;
const HIDDEN_INTERVAL_MS = 10000;

const ACTIVE_STATES = new Set([
  "transcribing",
  "reasoning",
  "acting",
  "responding",
  "speaking",
]);

export function sessionPollingInterval(status, isVisible = true) {
  if (!isVisible) return HIDDEN_INTERVAL_MS;
  const state = (status?.state || "").toLowerCase();
  return ACTIVE_STATES.has(state) ? ACTIVE_SESSION_INTERVAL_MS : IDLE_SESSION_INTERVAL_MS;
}

export function statusPollingInterval(isVisible = true) {
  return isVisible ? STATUS_INTERVAL_MS : HIDDEN_INTERVAL_MS;
}

export function createDesktopPolling({
  refreshSessionStatus,
  refreshResidentVoiceStatus,
  refreshWakeStatus,
}) {
  let sessionPollTimer = null;
  let residentVoicePollTimer = null;
  let wakePollTimer = null;
  let isPollingRunning = false;

  const isVisible = () => document.visibilityState !== "hidden";

  async function pollSession() {
    if (!isPollingRunning) return;
    sessionPollTimer = null;
    let status = null;
    try {
      status = await refreshSessionStatus();
    } catch {}
    if (isPollingRunning) {
      sessionPollTimer = window.setTimeout(pollSession, sessionPollingInterval(status, isVisible()));
    }
  }

  async function pollResidentVoice() {
    if (!isPollingRunning) return;
    residentVoicePollTimer = null;
    try {
      await refreshResidentVoiceStatus();
    } catch {}
    if (isPollingRunning) {
      residentVoicePollTimer = window.setTimeout(pollResidentVoice, statusPollingInterval(isVisible()));
    }
  }

  async function pollWake() {
    if (!isPollingRunning) return;
    wakePollTimer = null;
    try {
      await refreshWakeStatus();
    } catch {}
    if (isPollingRunning) {
      wakePollTimer = window.setTimeout(pollWake, statusPollingInterval(isVisible()));
    }
  }

  function rescheduleForVisibility() {
    if (!isPollingRunning) return;
    const delay = isVisible() ? 0 : HIDDEN_INTERVAL_MS;
    if (sessionPollTimer) {
      window.clearTimeout(sessionPollTimer);
      sessionPollTimer = window.setTimeout(pollSession, delay);
    }
    if (residentVoicePollTimer) {
      window.clearTimeout(residentVoicePollTimer);
      residentVoicePollTimer = window.setTimeout(pollResidentVoice, delay);
    }
    if (wakePollTimer) {
      window.clearTimeout(wakePollTimer);
      wakePollTimer = window.setTimeout(pollWake, delay);
    }
  }

  document.addEventListener("visibilitychange", rescheduleForVisibility);

  function startSessionPolling() {
    if (sessionPollTimer) window.clearTimeout(sessionPollTimer);
    isPollingRunning = true;
    pollSession();
  }

  function stopSessionPolling() {
    if (sessionPollTimer) {
      window.clearTimeout(sessionPollTimer);
      sessionPollTimer = null;
    }
  }

  function startResidentVoicePolling() {
    if (residentVoicePollTimer) window.clearTimeout(residentVoicePollTimer);
    isPollingRunning = true;
    pollResidentVoice();
  }

  function stopResidentVoicePolling() {
    if (residentVoicePollTimer) {
      window.clearTimeout(residentVoicePollTimer);
      residentVoicePollTimer = null;
    }
  }

  function startWakePolling() {
    if (wakePollTimer) window.clearTimeout(wakePollTimer);
    isPollingRunning = true;
    pollWake();
  }

  function stopWakePolling() {
    if (wakePollTimer) {
      window.clearTimeout(wakePollTimer);
      wakePollTimer = null;
    }
  }

  function startAllPolling() {
    isPollingRunning = true;
    startWakePolling();
    startSessionPolling();
    startResidentVoicePolling();
  }

  function stopAllPolling() {
    isPollingRunning = false;
    stopWakePolling();
    stopSessionPolling();
    stopResidentVoicePolling();
  }

  return {
    startSessionPolling,
    stopSessionPolling,
    startResidentVoicePolling,
    stopResidentVoicePolling,
    startWakePolling,
    stopWakePolling,
    startAllPolling,
    stopAllPolling,
  };
}
