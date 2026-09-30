// Formatting shared by every panel and the conversation, so a status, time, or error reads the
// same wherever it appears.

export function errorMessage(error, fallback = "Something went wrong.") {
  if (typeof error === "string") return error || fallback;
  return error?.detail?.message || error?.message || fallback;
}

export function isConflict(error) {
  return error?.status === 409 || error?.detail?.error === "conflict";
}

export function formatValue(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.length ? value.map(formatValue).join(", ") : "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function formatTime(value, { timeOnly = false } = {}) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return timeOnly ? date.toLocaleTimeString() : date.toLocaleString();
}

// Sentence-cases a backend enum ("awaiting_approval" -> "Awaiting approval") unless the map
// names it.
export function humanize(value, map = {}) {
  if (value === null || value === undefined || value === "") return "—";
  if (Object.prototype.hasOwnProperty.call(map, value)) return map[value];
  const words = String(value).replaceAll(/[-_]+/g, " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

const STATUS_TEXT = {
  awaiting_approval: "Waiting for approval",
  awaiting_input: "Waiting for your answer",
  approval_required: "Waiting for approval",
  allowed: "Allowed to run",
  denied: "Declined",
  running: "Running",
  success: "Completed",
  succeeded: "Completed",
  failure: "Failed",
  failed: "Failed",
  cancelled: "Cancelled",
  outcome_unknown: "Outcome unknown - it may have taken effect; check before repeating it",
  enabled: "Enabled",
  disabled: "Disabled",
  retired: "Retired",
  ready: "Ready",
  degraded: "Degraded",
  unavailable: "Unavailable",
};

export function statusText(status) {
  return humanize(status, STATUS_TEXT);
}

// One colour vocabulary for status badges and chips: ready, succeeded, running, degraded,
// blocked, failed, cancelled, idle.
const STATUS_STATE = {
  success: "succeeded",
  succeeded: "succeeded",
  completed: "succeeded",
  ready: "ready",
  enabled: "ready",
  allowed: "ready",
  running: "running",
  awaiting_input: "running",
  awaiting_approval: "degraded",
  approval_required: "degraded",
  degraded: "degraded",
  outcome_unknown: "degraded",
  disabled: "blocked",
  retired: "blocked",
  unavailable: "blocked",
  denied: "blocked",
  blocked: "blocked",
  failure: "failed",
  failed: "failed",
  cancelled: "cancelled",
};

export function statusState(status) {
  return STATUS_STATE[status] || "idle";
}
