// In-app modal confirmation dialog rendered through the HTML <dialog> API.
// Non-blocking, accessible, styled to match JARVISv7 dark tokens, and preserves
// background polling during destructive action prompts.

import { button, buttonRow } from "./dom.js";

export function showConfirmDialog({
  title = "Confirm Action",
  message = "Are you sure you want to proceed?",
  confirmLabel = "Confirm",
  confirmVariant = "danger",
  cancelLabel = "Cancel",
} = {}) {
  return new Promise((resolve) => {
    const dialog = document.createElement("dialog");
    dialog.className = "confirm-dialog";
    dialog.setAttribute("aria-labelledby", "confirm-dialog-title");

    const header = document.createElement("div");
    header.className = "confirm-dialog-header";
    const heading = document.createElement("h3");
    heading.id = "confirm-dialog-title";
    heading.textContent = title;
    header.appendChild(heading);

    const body = document.createElement("div");
    body.className = "confirm-dialog-body";
    const text = document.createElement("p");
    text.textContent = message;
    body.appendChild(text);

    let settled = false;
    function finish(value) {
      if (settled) return;
      settled = true;
      try {
        dialog.close();
      } catch {
        // no-op if already closed
      }
      dialog.remove();
      resolve(value);
    }

    const cancelBtn = button(cancelLabel, {
      onClick: () => finish(false),
      focusKey: "confirm:cancel",
    });

    const confirmBtn = button(confirmLabel, {
      variant: confirmVariant,
      onClick: () => finish(true),
      focusKey: "confirm:action",
    });

    const footer = buttonRow(cancelBtn, confirmBtn);
    footer.className = "confirm-dialog-actions panel-buttons";

    dialog.append(header, body, footer);

    dialog.addEventListener("cancel", (event) => {
      event.preventDefault();
      finish(false);
    });

    document.body.appendChild(dialog);

    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      // Fallback in headless/mock environments lacking showModal
      dialog.setAttribute("open", "");
    }

    cancelBtn.focus();
  });
}
