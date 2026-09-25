import { test } from "node:test";
import { strict as assert } from "node:assert";
import { createAdvancedPanelCoordinator } from "../src/components/advanced-panel.js";
import { index, style } from "./support.mjs";

test("desktop markup must not use inline styles", async () => {
  const tokenStart = "/* JARVIS_V7_TOKENS_START */";
  const tokenEnd = "/* JARVIS_V7_TOKENS_END */";
  assert.equal(style.split("JARVIS_V7_TOKENS_START").length - 1, 1);
  assert.equal(style.split("JARVIS_V7_TOKENS_END").length - 1, 1);
  assert.ok(style.indexOf(tokenStart) < style.indexOf(tokenEnd));
  for (const token of [
    "--color-bg-base",
    "--color-accent",
    "--color-ready",
    "--color-degraded",
    "--color-failed",
    "--color-capture",
    "--color-text-primary",
    "--space-1",
  ]) {
    assert.ok(style.includes(token), `style token missing: ${token}`);
  }
  const outsideTokens = style.slice(0, style.indexOf(tokenStart)) + style.slice(style.indexOf(tokenEnd) + tokenEnd.length);
  assert.doesNotMatch(outsideTokens, /#[0-9a-fA-F]{3,8}\b/);
  for (const rawColorFunction of ["rgb(", "rgba(", "hsl(", "hsla("]) {
    assert.ok(!outsideTokens.includes(rawColorFunction), `raw color function outside token section: ${rawColorFunction}`);
  }
  for (const selector of [
    '[data-state="LISTENING"]',
    '[data-state="REASONING"]',
    '[data-state="SPEAKING"]',
    '[data-state="DEGRADED"]',
    '[data-state="FAILED"]',
    '[data-capture-state="recording"]',
    '[data-capture-state="processing"]',
    'data-readiness-state="ready"',
    'data-readiness-state="degraded"',
    'data-readiness-state="failed"',
    ".degraded-condition",
    "capture-pulse",
    ".message.user",
    ".message.assistant",
    ".message.system",
    ".message.presence",
  ]) {
    assert.ok(style.includes(selector), `desktop style contract missing: ${selector}`);
  }
  assert.ok(!index.includes(" style="), "desktop markup must not use inline styles");
  const textForm = index.match(/<form id="text-form"[\s\S]*?<\/form>/)?.[0] || "";
  assert.ok(textForm.includes('id="text-input"') && textForm.includes('id="send-button"'));
  assert.ok(!textForm.includes('id="search-status"') && !textForm.includes('id="search-stop"'), "search progress must not occupy composer grid cells");
  assert.ok(style.includes("grid-template-columns: minmax(220px, 280px) minmax(320px, 1fr) minmax(260px, 340px);"));
  for (const selector of [
    ".status-panel",
    ".conversation-panel",
    ".operator-panel",
    ".panel-section",
    ".operator-header",
    ".operator-actions",
    ".settings-panel",
    ".appearance-panel",
  ]) {
    assert.ok(style.includes(selector), `desktop layout contract missing: ${selector}`);
  }
  assert.match(style, /\.status-panel\s*{\s*overflow-y:\s*auto;/);
  assert.match(style, /\.operator-panel\s*{[\s\S]*overflow:\s*hidden;/);
  assert.ok(style.includes("@media (max-width: 820px)"));
  for (const selector of [
    ".advanced-panel",
    ".advanced-panel::backdrop",
    ".advanced-panel-rail",
    '.advanced-panel-rail button[aria-selected="true"]',
    ".advanced-panel-detail",
    ".extensions-panel-layout",
    ".extensions-panel-list",
    ".extensions-panel-detail",
    ".agents-panel",
    "--color-backdrop",
  ]) {
    assert.ok(style.includes(selector), `advanced-control style contract missing: ${selector}`);
  }
});

test("Personality must share the operator-panel selector sizing once it moves to the right sidebar", async () => {
  assert.ok(
    !style.includes(".status-panel #personality-select"),
    "Personality must share the operator-panel selector sizing once it moves to the right sidebar",
  );
});

test("System State must be sized to the operator column", async () => {
  assert.ok(index.includes("system-state-card"), "desktop must size System State to Operator column");
});

test("every advanced-control category must be registered, including Agents and Providers & Models", async () => {
  const panelEvents = [];
  let dismissals = 0;
  function advancedCategory(id, openInitially = false) {
    let open = openInitially;
    return {
      id,
      isOpen: () => open,
      open: async () => {
        panelEvents.push(`open-${id}`);
        open = true;
      },
      close: () => {
        panelEvents.push(`close-${id}`);
        open = false;
      },
    };
  }
  const advancedCategories = [
    advancedCategory("providers"),
    advancedCategory("settings", true),
    advancedCategory("memory"),
    advancedCategory("actions"),
    advancedCategory("extensions"),
    advancedCategory("agents"),
  ];
  const coordinator = createAdvancedPanelCoordinator({
    categories: advancedCategories,
    dismiss: () => {
      dismissals += 1;
      coordinator.closeActive();
    },
  });
  assert.deepEqual(
    coordinator.categoryIds(),
    ["providers", "settings", "memory", "actions", "extensions", "agents"],
    "every advanced-control category must be registered, including Agents and Providers & Models",
  );
  assert.equal(coordinator.activeCategoryId(), "settings", "the rail must report which category is showing");

  await coordinator.openCategory("memory");
  assert.deepEqual(panelEvents, ["close-settings", "open-memory"], "memory open must deterministically close settings first");
  assert.equal(coordinator.activeCategoryId(), "memory");
  panelEvents.length = 0;

  await coordinator.openCategory("agents");
  assert.deepEqual(panelEvents, ["close-memory", "open-agents"], "a rail is single-select, so switching must close the previous category");
  panelEvents.length = 0;

  await coordinator.openCategory("agents");
  assert.deepEqual(panelEvents, [], "re-selecting the showing category must not remount it");
  await coordinator.openCategory("nonexistent");
  assert.deepEqual(panelEvents, [], "an unknown category must be ignored rather than closing the surface");

  coordinator.requestClose();
  assert.deepEqual(panelEvents, ["close-agents"], "dismissal must close whichever category is showing");
  assert.equal(dismissals, 1);
  assert.equal(coordinator.activeCategoryId(), "", "nothing may stay mounted after dismissal");
  panelEvents.length = 0;

  coordinator.requestClose();
  assert.deepEqual(panelEvents, [], "dismissing an already-dismissed surface must be a no-op");
});

test("A category's own Close button reports through onClose, which asks the host to dismiss. That report must...", async () => {
  // A category's own Close button reports through onClose, which asks the host to dismiss. That
  // report must not re-enter as a second dismissal, and it must not fire during a rail switch.
  const reentrantEvents = [];
  let reentrantDismissals = 0;
  const reentrant = [];
  function reentrantCategory(id, openInitially = false) {
    let open = openInitially;
    return {
      id,
      isOpen: () => open,
      open: async () => {
        reentrantEvents.push(`open-${id}`);
        open = true;
      },
      close: () => {
        reentrantEvents.push(`close-${id}`);
        open = false;
        reentrantCoordinator.requestClose();
      },
    };
  }
  reentrant.push(reentrantCategory("memory", true), reentrantCategory("agents"));
  const reentrantCoordinator = createAdvancedPanelCoordinator({
    categories: reentrant,
    dismiss: () => {
      reentrantDismissals += 1;
      reentrantCoordinator.closeActive();
    },
  });
  await reentrantCoordinator.openCategory("agents");
  assert.deepEqual(reentrantEvents, ["close-memory", "open-agents"], "a category switch must not dismiss the whole surface");
  assert.equal(reentrantDismissals, 0, "closing a category to switch rails is not a dismissal");
  reentrantEvents.length = 0;
  reentrantCoordinator.closeActive();
  assert.deepEqual(reentrantEvents, ["close-agents"], "teardown must close each category exactly once");
  assert.equal(reentrantDismissals, 0, "an onClose report during teardown must not re-enter as a new dismissal");
});
