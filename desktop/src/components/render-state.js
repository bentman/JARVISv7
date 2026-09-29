// Panels re-render by replacing their whole DOM, so anything the operator is holding -
// an unsent draft, a scrolled list, the control they just clicked - must be captured from
// the outgoing tree and reapplied to the incoming one. Fields opt in with
// data-draft-key, scroll containers with data-scroll-key, and focusable controls with
// data-focus-key; keys must be stable across renders.

export function captureRenderState(container) {
  const active = document.activeElement;
  return {
    drafts: new Map([...container.querySelectorAll("[data-draft-key]")].map((field) => [
      field.dataset.draftKey,
      { value: field.value, checked: field.checked, focused: active === field },
    ])),
    scroll: new Map([...container.querySelectorAll("[data-scroll-key]")].map((node) => [node.dataset.scrollKey, node.scrollTop])),
    focusKey: active?.dataset?.focusKey,
  };
}

export function restoreRenderState(container, snapshot) {
  for (const field of container.querySelectorAll("[data-draft-key]")) {
    const draft = snapshot.drafts.get(field.dataset.draftKey);
    if (!draft) continue;
    field.value = draft.value;
    if (field.type === "checkbox") field.checked = draft.checked;
    if (draft.focused) field.focus({ preventScroll: true });
  }
  if (snapshot.focusKey) {
    for (const node of container.querySelectorAll("[data-focus-key]")) {
      if (node.dataset.focusKey === snapshot.focusKey) {
        node.focus({ preventScroll: true });
        break;
      }
    }
  }
  for (const node of container.querySelectorAll("[data-scroll-key]")) {
    const saved = snapshot.scroll.get(node.dataset.scrollKey);
    if (saved !== undefined) node.scrollTop = saved;
  }
}

// A panel's DOM is discarded when its Advanced Controls category closes. retain() keeps the
// outgoing state so the next open restores it; it wins over the fresh render until release(),
// which the panel calls once its reopened data has loaded and the retained fields exist again.
export function createRenderStateKeeper(container) {
  let retained = null;
  return {
    render(...children) {
      const current = captureRenderState(container);
      const snapshot = retained
        ? {
          drafts: new Map([...current.drafts, ...retained.drafts]),
          scroll: new Map([...current.scroll, ...retained.scroll]),
          focusKey: retained.focusKey || current.focusKey,
        }
        : current;
      container.replaceChildren(...children);
      restoreRenderState(container, snapshot);
    },
    retain() {
      retained = captureRenderState(container);
    },
    release() {
      retained = null;
    },
  };
}
