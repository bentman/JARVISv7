export function createDesktopPolling({
  refreshSessionStatus,
  refreshResidentVoiceStatus,
  refreshWakeStatus,
}) {
  let sessionPollTimer = null;
  let residentVoicePollTimer = null;
  let wakePollTimer = null;

  function startSessionPolling() {
    if (sessionPollTimer) window.clearInterval(sessionPollTimer);
    sessionPollTimer = window.setInterval(() => {
      refreshSessionStatus().catch(() => undefined);
    }, 1000);
  }

  function stopSessionPolling() {
    if (!sessionPollTimer) return;
    window.clearInterval(sessionPollTimer);
    sessionPollTimer = null;
  }

  function startResidentVoicePolling() {
    if (residentVoicePollTimer) window.clearInterval(residentVoicePollTimer);
    residentVoicePollTimer = window.setInterval(() => {
      refreshResidentVoiceStatus().catch(() => undefined);
    }, 1500);
  }

  function stopResidentVoicePolling() {
    if (!residentVoicePollTimer) return;
    window.clearInterval(residentVoicePollTimer);
    residentVoicePollTimer = null;
  }

  function startWakePolling() {
    if (wakePollTimer) window.clearInterval(wakePollTimer);
    wakePollTimer = window.setInterval(() => {
      refreshWakeStatus().catch(() => undefined);
    }, 1500);
  }

  function stopWakePolling() {
    if (!wakePollTimer) return;
    window.clearInterval(wakePollTimer);
    wakePollTimer = null;
  }

  function startAllPolling() {
    startWakePolling();
    startSessionPolling();
    startResidentVoicePolling();
  }

  function stopAllPolling() {
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
