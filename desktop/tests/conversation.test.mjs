import { test } from "node:test";
import { strict as assert } from "node:assert";
import { createConversation } from "../src/components/conversation.js";
import { createElement } from "./support.mjs";

test("approval keyboard shortcuts must be isolated from inputs and clean up on card removal", async () => {
  const previousDocument = globalThis.document;
  const previousWindow = globalThis.window;

  const windowListeners = new Map();
  globalThis.window = {
    addEventListener(name, handler) {
      windowListeners.set(name, handler);
    },
    removeEventListener(name, handler) {
      if (windowListeners.get(name) === handler) {
        windowListeners.delete(name);
      }
    },
  };

  const activeInput = createElement("input");
  globalThis.document = {
    createElement,
    activeElement: activeInput,
    querySelector: () => null,
  };

  try {
    const logEl = createElement("div");
    const decisions = [];
    const conversation = createConversation({
      logEl,
      decide: async (proposalId, outcome) => {
        decisions.push([proposalId, outcome]);
      },
    });

    const pending = { proposal_id: "prop-1", capability_id: "system-write", label: "Write file" };
    conversation.renderPending(pending);

    const onKeydown = windowListeners.get("keydown");
    assert.ok(typeof onKeydown === "function", "keydown listener must be attached to window");

    // When focus is in an input, Ctrl+Enter and Escape must NOT decide the proposal
    let prevented = false;
    onKeydown({
      ctrlKey: true,
      key: "Enter",
      preventDefault: () => { prevented = true; },
    });
    assert.deepEqual(decisions, [], "Ctrl+Enter must not approve while typing in input");
    assert.equal(prevented, false);

    onKeydown({
      key: "Escape",
      preventDefault: () => { prevented = true; },
    });
    assert.deepEqual(decisions, [], "Escape must not decline while typing in input");

    // When focus is NOT in an input, Ctrl+Enter approves
    globalThis.document.activeElement = logEl;
    onKeydown({
      ctrlKey: true,
      key: "Enter",
      preventDefault: () => { prevented = true; },
    });
    await new Promise((resolve) => setImmediate(resolve));
    assert.deepEqual(decisions, [["prop-1", "approved"]], "Ctrl+Enter must approve when input is not focused");

    // Clearing pending approval removes card and unhooks listener
    conversation.renderPending(null);
    assert.equal(windowListeners.has("keydown"), false, "keydown listener must be cleaned up on pending dismissal");
  } finally {
    globalThis.document = previousDocument;
    globalThis.window = previousWindow;
  }
});
