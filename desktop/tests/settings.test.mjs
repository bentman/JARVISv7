import { test } from "node:test";
import { strict as assert } from "node:assert";
import { clearRestartRequired, markRestartRequired, restartRequiredScopes, restartScopeDisables } from "../src/components/settings-panel.js";
import { createAppearanceControls } from "../src/components/appearance-controls.js";
import { builtinProfileNotice, defaultEditingProfile, providerChoiceGroups, providerRestartDisabled, providerSelectionPayload } from "../src/components/llm-provider-settings.js";
import { style, createElement, findElements } from "./support.mjs";

test("the provider editor must open on an editable profile instead of a read-only built-in", async () => {
  const builtinManaged = { profile_id: "builtin:managed-llama-cpp", name: "managed llama.cpp", kind: "managed_llama_cpp", builtin: true };
  const editableLab = { profile_id: "lab", name: "Lab", kind: "openai_compatible" };
  const editableCloud = { profile_id: "cloud", name: "Cloud", kind: "openai", cloud_eligible: true };
  const builtinSelection = { primary_profile_id: "builtin:managed-llama-cpp" };
  assert.equal(
    defaultEditingProfile([builtinManaged, editableLab], builtinSelection)?.profile_id,
    "lab",
    "the provider editor must open on an editable profile instead of a read-only built-in",
  );
  assert.equal(
    defaultEditingProfile([builtinManaged, editableLab, editableCloud], builtinSelection, "cloud")?.profile_id,
    "cloud",
    "the acted-on profile must stay selected after a create or update reload",
  );
  assert.equal(
    defaultEditingProfile([builtinManaged], builtinSelection)?.profile_id,
    "builtin:managed-llama-cpp",
    "with no editable profile the selected built-in is still shown",
  );
  assert.equal(defaultEditingProfile([], {})?.profile_id, undefined, "an empty catalog must resolve to no profile");
  assert.equal(defaultEditingProfile(null, null), null);
  assert.ok(
    builtinProfileNotice(builtinManaged).includes("cannot be edited"),
    "a built-in profile must explain why its controls are read-only",
  );
  assert.equal(builtinProfileNotice(editableLab), "", "an editable profile must not claim to be read-only");
  assert.equal(providerRestartDisabled(["operator"]), false, "an operator-config save must not freeze provider controls");
  assert.equal(providerRestartDisabled(["provider"]), true);
  assert.equal(providerRestartDisabled(new Set(["operator", "provider"])), true);
  assert.equal(providerRestartDisabled([]), false);
});

test("provider selection payloads and choice groups must follow profile eligibility", async () => {
  assert.deepEqual(providerSelectionPayload("primary", "", false, "cloud"), {
    primary_profile_id: "primary",
    local_fallback_profile_id: null,
    cloud_escalation_enabled: false,
    cloud_profile_id: "cloud",
  });
  assert.deepEqual(
    providerChoiceGroups([
      { profile_id: "managed", kind: "managed_llama_cpp", cloud_eligible: false },
      { profile_id: "private-compatible", kind: "openai_compatible", cloud_eligible: false },
      { profile_id: "public-compatible", kind: "openai_compatible", cloud_eligible: true },
      { profile_id: "openai", kind: "openai", cloud_eligible: true },
    ]),
    { local: ["managed", "private-compatible"], cloud: ["public-compatible", "openai"] },
  );
});

test("appearance controls must render font, density, and accent selectors", async () => {
  const previousDocument = globalThis.document;
  globalThis.document = { createElement };
  try {
    // appearance-controls.js tests
    const section = createAppearanceControls();
    assert.ok(String(section.className).includes("appearance-panel"), "appearance panel must have correct class");
    const selects = findElements(section, (n) => n.tagName === "select");
    assert.equal(selects.length, 3, "must render Font, Density, and Accent selectors");
    const labels = findElements(section, (n) => n.tagName === "label");
    assert.ok(labels[0].children[0].textContent.includes("Font"), "must render Font label");
    assert.ok(labels[1].children[0].textContent.includes("Density"), "must render Density label");
    assert.ok(labels[2].children[0].textContent.includes("Accent"), "must render Accent label");
    
    let propertySet = false;
    const previousDocumentElement = globalThis.document.documentElement;
    globalThis.document.documentElement = {
      style: { setProperty: () => { propertySet = true; } }
    };
    
    selects[0].listeners.change();
    assert.ok(propertySet, "appearance change must update documentElement styles");
    
    globalThis.document.documentElement = previousDocumentElement;
  } finally {
    globalThis.document = previousDocument;
  }
});

test("a restart-required mark must disable only its own scope until cleared", async () => {
  clearRestartRequired();
  markRestartRequired("provider");
  markRestartRequired("provider");
  assert.deepEqual(restartRequiredScopes(), ["provider"]);
  assert.equal(restartScopeDisables(restartRequiredScopes(), "provider"), true);
  assert.equal(restartScopeDisables(restartRequiredScopes(), "operator"), false);
  clearRestartRequired();
  assert.deepEqual(restartRequiredScopes(), []);
});
