// Every destructive operator action confirms through this one prompt. Panels take it through
// their options so tests can answer it.
export function confirmDestructive(message) {
  return Promise.resolve(window.confirm(message));
}
