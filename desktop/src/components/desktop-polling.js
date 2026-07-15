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
  refreshDesktopStatus,
}) {
  let pollTimer = null;
  let isPollingRunning = false;
  let lastStatusPollAt = 0;

  const isVisible = () => document.visibilityState !== "hidden";

  async function pollDesktopStatus() {
    if (!isPollingRunning) return;
    pollTimer = null;
    let status = null;
    const now = Date.now();
    const refreshFullStatus = lastStatusPollAt === 0 || now - lastStatusPollAt >= statusPollingInterval(isVisible());
    if (refreshFullStatus) lastStatusPollAt = now;
    try {
      status = refreshFullStatus ? await refreshDesktopStatus() : await refreshSessionStatus();
    } catch {}
    if (!isPollingRunning) return;
    pollTimer = window.setTimeout(pollDesktopStatus, sessionPollingInterval(status, isVisible()));
  }

  function rescheduleForVisibility() {
    if (!isPollingRunning) return;
    const delay = isVisible() ? 0 : HIDDEN_INTERVAL_MS;
    if (pollTimer) window.clearTimeout(pollTimer);
    pollTimer = window.setTimeout(pollDesktopStatus, delay);
  }

  document.addEventListener("visibilitychange", rescheduleForVisibility);

  function startAllPolling() {
    if (pollTimer) window.clearTimeout(pollTimer);
    isPollingRunning = true;
    lastStatusPollAt = 0;
    pollDesktopStatus();
  }

  function stopAllPolling() {
    isPollingRunning = false;
    if (pollTimer) {
      window.clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  return {
    startAllPolling,
    stopAllPolling,
  };
}
