// The frame every Advanced Controls panel shares: header, message region, section states, and a
// lifecycle that keeps drafts, scroll, and focus across refreshes and category switches.
import { createRenderStateKeeper } from "../render-state.js";
import { appendText } from "./dom.js";
import { TEXT } from "./vocabulary.js";

export function renderPanelHeader(title) {
  const header = document.createElement("div");
  header.className = "panel-header";
  const heading = appendText(header, title, "h2");
  heading.tabIndex = -1;
  return header;
}

// Notices and errors are separate channels announced to assistive technology.
export function messageRegion({ notice = "", error = "" } = {}) {
  const region = document.createElement("div");
  region.setAttribute("aria-live", "polite");
  if (notice) appendText(region, notice, "p", "panel-notice");
  if (error) appendText(region, error, "p", "panel-error");
  return region;
}

export function section(title) {
  const node = document.createElement("section");
  node.className = "panel-box";
  if (title) appendText(node, title, "h3");
  return node;
}

// Renders the loading, error, or empty line for a section. Returns true when it rendered one,
// so the caller stops there.
export function sectionState(parent, { loading = false, error = "", empty = false, thing = "items" }) {
  if (loading) {
    appendText(parent, TEXT.loading(thing), "p", "panel-help");
    return true;
  }
  if (error) {
    appendText(parent, error, "p", "panel-error");
    return true;
  }
  if (empty) {
    appendText(parent, TEXT.empty(thing), "p", "panel-help");
    return true;
  }
  return false;
}

// `render(state)` returns the panel's children. `poll`, when given, runs every second while
// `poll.active()` is true and no field has focus, so typing is never interrupted.
export function createPanelLifecycle(container, { load, render, cancelPendingReads = () => {}, onClose, poll = null }) {
  const keeper = createRenderStateKeeper(container);
  let open = false;
  let timer = null;
  let latest = null;

  function draw(state) {
    latest = state;
    if (open) keeper.render(...render(state));
  }

  async function show() {
    open = true;
    container.hidden = false;
    if (latest) keeper.render(...render(latest));
    await load();
    keeper.release();
    if (poll) {
      timer = window.setInterval(() => {
        if (!poll.active()) return;
        const active = document.activeElement;
        if (active && ["INPUT", "TEXTAREA", "SELECT"].includes(active.tagName)) return;
        poll.run();
      }, 1000);
    }
    container.querySelector("h2")?.focus();
  }

  function close() {
    if (!open) return;
    open = false;
    cancelPendingReads();
    if (timer) {
      window.clearInterval(timer);
      timer = null;
    }
    keeper.retain();
    container.hidden = true;
    container.replaceChildren();
    onClose?.();
  }

  return { draw, open: show, close, isOpen: () => open };
}
