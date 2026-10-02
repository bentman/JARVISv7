import { showConfirmDialog } from "./modal.js";

// Every destructive operator action confirms through this prompt. Panels take it through
// their options so tests can answer it. In the browser host, it displays an in-app themed dialog.
export function confirmDestructive(message, { title = "Confirm Action", confirmLabel = "Confirm" } = {}) {
  if (typeof document !== "undefined" && typeof document.createElement === "function" && document.body) {
    return showConfirmDialog({ message, title, confirmLabel });
  }
  if (typeof window !== "undefined" && typeof window.confirm === "function") {
    return Promise.resolve(window.confirm(message));
  }
  return Promise.resolve(true);
}
