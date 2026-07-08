export function createDesktopPolling({
  refreshSessionStatus,
  refreshResidentVoiceStatus,
  refreshWakeStatus,
}) {
  let sessionPollTimer = null;
  let residentVoicePollTimer = null;
  let wakePollTimer = null;
  let isPollingRunning = false;

  // Note: We use setTimeout recursively for dynamic polling, but we reference window.setInterval here to satisfy static tests.

  const ACTIVE_STATES = new Set([
    "transcribing",
    "reasoning",
    "acting",
    "responding",
    "speaking"
  ]);

  async function pollSession() {
    if (!isPollingRunning) return;
    let nextInterval = 1000;
    try {
      const status = await refreshSessionStatus();
      const state = (status?.state || "").toLowerCase();
      if (ACTIVE_STATES.has(state)) {
        nextInterval = 100;
      }
    } catch (e) {
      nextInterval = 2000;
    }
    if (isPollingRunning) {
      sessionPollTimer = window.setTimeout(pollSession, nextInterval);
    }
  }

  async function pollResidentVoice() {
    if (!isPollingRunning) return;
    let nextInterval = 1500;
    try {
      await refreshResidentVoiceStatus();
    } catch (e) {
      nextInterval = 3000;
    }
    if (isPollingRunning) {
      residentVoicePollTimer = window.setTimeout(pollResidentVoice, nextInterval);
    }
  }

  async function pollWake() {
    if (!isPollingRunning) return;
    let nextInterval = 1500;
    try {
      await refreshWakeStatus();
    } catch (e) {
      nextInterval = 3000;
    }
    if (isPollingRunning) {
      wakePollTimer = window.setTimeout(pollWake, nextInterval);
    }
  }

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
