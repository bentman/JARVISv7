export function renderDegradedList(readinessPayload, containerEl) {
  if (!containerEl) return;

  containerEl.replaceChildren();
  containerEl.hidden = true;
}
