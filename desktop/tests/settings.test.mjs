import { test } from "node:test";
import { strict as assert } from "node:assert";
import { clearRestartRequired, markRestartRequired, restartRequiredScopes, restartScopeDisables, closeSettings, openSettings } from "../src/components/settings-panel.js";
import { createAppearanceControls } from "../src/components/appearance-controls.js";
import { builtinProfileNotice, defaultEditingProfile, providerChoiceGroups, providerRestartDisabled, providerSelectionPayload, createLlmProviderSettings, openProviderSettings, PROVIDER_TYPES, profileToProviderType } from "../src/components/llm-provider-settings.js";
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

test("operator settings must render sections, choices, and advanced fields from backend metadata", async () => {
  const previousDocument = globalThis.document;
  // Browsers report upper-case tag names, and the settings panel branches on that.
  globalThis.document = { createElement: (tag) => Object.assign(createElement(tag), { tagName: tag.toUpperCase() }) };
  try {
    const container = createElement("div");
    await openSettings(container, {
      getOperatorConfig: async () => ({ fields: [
        { key: "USE_DDGS", section: "Search", value: "false", options: ["true", "false"], editable: true },
        { key: "SEARCH_TIMEOUT_S", section: "Search", value: "20", advanced: true, editable: true },
      ] }),
    });
    const headings = findElements(container, (node) => node.tagName === "H3").map((node) => node.textContent);
    assert.ok(headings.includes("Search"), "fields must be grouped under their backend section");
    const select = findElements(container, (node) => node.tagName === "SELECT" && node.name === "USE_DDGS")[0];
    assert.deepEqual(select.children.map((option) => option.value), ["true", "false"], "choices must come from backend options");
    assert.equal(select.value, "false");
    assert.equal(select.dataset.draftKey, "setting:USE_DDGS", "an unsaved edit must survive a re-render");
    const advanced = findElements(container, (node) => node.tagName === "DETAILS")[0];
    assert.ok(findElements(advanced, (node) => node.name === "SEARCH_TIMEOUT_S").length === 1, "advanced fields must sit behind a disclosure");
    closeSettings();
  } finally {
    globalThis.document = previousDocument;
  }
});

test("the provider section must offer escalation, connection testing, and credential removal", async () => {
  const previousDocument = globalThis.document;
  globalThis.document = { createElement };
  try {
    const section = createLlmProviderSettings({
      profiles: [{ profile_id: "lab", name: "Lab", kind: "openai_compatible", readiness_state: "configured" }],
      selection: { primary_profile_id: "lab" },
    }, {});
    const texts = findElements(section, (node) => typeof node.textContent === "string").map((node) => node.textContent);
    for (const label of ["Model providers", "Allow cloud escalation", "Test connection", "Remove stored credential"]) {
      assert.ok(texts.includes(label), `the provider section must render ${label}`);
    }
    assert.equal(typeof openProviderSettings, "function", "Providers & Models must be mountable as its own category");
  } finally {
    globalThis.document = previousDocument;
  }
});

test("provider types must include Unsloth defaulting to port 4444 and support profile duplication and deletion guard", async () => {
  assert.ok(PROVIDER_TYPES.unsloth, "Unsloth provider type must exist");
  assert.equal(PROVIDER_TYPES.unsloth.endpoint, "http://127.0.0.1:4444/v1", "Unsloth must default to port 4444");
  assert.equal(PROVIDER_TYPES.unsloth.kind, "openai_compatible", "Unsloth must map to openai_compatible");

  assert.equal(profileToProviderType({ kind: "openai_compatible", endpoint: "http://127.0.0.1:4444/v1" }), "unsloth");
  assert.equal(profileToProviderType({ kind: "openai_compatible", endpoint: "http://127.0.0.1:8080/v1" }), "llama_cpp");
  assert.equal(profileToProviderType({ kind: "ollama" }), "ollama");

  const previousDocument = globalThis.document;
  globalThis.document = { createElement };
  try {
    const primaryProfile = { profile_id: "primary-1", name: "Primary Local", kind: "openai_compatible", endpoint: "http://127.0.0.1:4444/v1", context_window: 8192, timeout_seconds: 60 };
    const unusedProfile = { profile_id: "custom-2", name: "Custom Extra", kind: "openai_compatible", endpoint: "http://127.0.0.1:8080/v1", context_window: 4096, timeout_seconds: 30 };
    const section = createLlmProviderSettings({
      profiles: [primaryProfile, unusedProfile],
      selection: { primary_profile_id: "primary-1" },
    }, {});

    const buttons = findElements(section, (n) => n.tagName === "button");
    const duplicateBtn = buttons.find((n) => n.textContent === "Duplicate");
    assert.ok(duplicateBtn, "Duplicate button must be rendered in profile toolbar");

    const newBtn = buttons.find((n) => n.textContent === "New profile");
    assert.ok(newBtn, "New profile button must be rendered");

    // Primary profile is active, so delete button must be guarded/disabled
    const deleteBtn = buttons.find((n) => n.textContent === "Delete profile");
    assert.ok(deleteBtn, "Delete profile button must exist");
    assert.equal(deleteBtn.disabled, true, "active primary profile must not be deletable");

    // Verify Provider type options are alphabetized
    const selects = findElements(section, (n) => n.tagName === "select");
    const profileSelect = selects.find((s) => s.parentElement?.children?.[0]?.textContent === "Profile");
    const typeSelect = selects.find((s) => s.parentElement?.children?.[0]?.textContent === "Provider type");
    assert.ok(typeSelect, "Provider type selector must exist");
    const optionLabels = typeSelect.children.map((o) => o.textContent);
    const sortedOptionLabels = [...optionLabels].sort((a, b) => a.localeCompare(b));
    assert.deepEqual(optionLabels, sortedOptionLabels, "Provider type options must be alphabetized");

    // Verify Provider type field appears before Display name in fields list
    const labels = findElements(section, (n) => n.tagName === "label");
    const labelTexts = labels.map((l) => l.children?.[0]?.textContent).filter(Boolean);
    const typeIdx = labelTexts.indexOf("Provider type");
    const nameIdx = labelTexts.indexOf("Display name");
    assert.ok(typeIdx !== -1 && nameIdx !== -1 && typeIdx < nameIdx, "Provider type must appear before Display name in fields list");

    // Clicking New Profile must populate standard primary local defaults (llama.cpp)
    newBtn.click();
    const inputs = findElements(section, (n) => n.tagName === "input");
    const endpointInput = inputs.find((n) => n.value === "http://127.0.0.1:8080/v1");
    assert.ok(endpointInput, "New profile must populate primary local default endpoint");
    const nameInput = inputs.find((n) => n.parentElement?.children?.[0]?.textContent === "Display name");
    assert.equal(nameInput.value, "llama.cpp Local", "New profile must default Display name to llama.cpp Local");

    // Changing Provider type must automatically adjust Display name and Model defaults
    const modelInput = inputs.find((n) => n.list === "llm-provider-models");
    typeSelect.value = "unsloth";
    typeSelect.listeners.change?.();
    assert.equal(nameInput.value, "Unsloth Local", "Display name must adjust to Unsloth Local");
    assert.equal(endpointInput.value, "http://127.0.0.1:4444/v1", "Endpoint must adjust to Unsloth port 4444");

    typeSelect.value = "ollama";
    typeSelect.listeners.change?.();
    assert.equal(nameInput.value, "Ollama Local", "Display name must adjust with Provider type");
    assert.equal(modelInput.value, "llama3.2", "Model must adjust with Ollama Provider type");

    typeSelect.value = "anthropic";
    typeSelect.listeners.change?.();
    assert.equal(nameInput.value, "Anthropic Cloud", "Display name must adjust with Provider type");
    assert.equal(modelInput.value, "claude-sonnet-5-5", "Model must adjust with Anthropic Provider type");

    typeSelect.value = "llama_cpp";
    typeSelect.listeners.change?.();
    assert.equal(nameInput.value, "llama.cpp Local", "Display name must adjust back to llama.cpp Local");
    assert.equal(modelInput.value, "default", "Model must reset back to default, not stuck on Anthropic");

    // Clicking Duplicate on custom-2 must clone into editable copy
    profileSelect.value = "custom-2";
    profileSelect.listeners.change?.();
    duplicateBtn.click();
    assert.equal(nameInput.value, "Custom Extra (Copy)", "Duplicate must create an editable draft with (Copy) suffix");

    // Test connection must be enabled on new/draft profiles and send draft payload
    let testCall = null;
    const testHandlers = {
      testLlmProfile: async (id, payload) => {
        testCall = { id, payload };
        return {
          status: "ready",
          reason: "provider models endpoint reachable",
          models: [{ id: "nemotron-3-nano:4b" }, { id: "omnicoder-9b:q6_k" }],
        };
      },
    };
    const draftSection = createLlmProviderSettings({
      profiles: [primaryProfile],
      selection: { primary_profile_id: "primary-1" },
    }, testHandlers);
    const draftButtons = findElements(draftSection, (n) => n.tagName === "button");
    const draftNewBtn = draftButtons.find((n) => n.textContent === "New profile");
    const draftTestBtn = draftButtons.find((n) => n.textContent === "Test connection");
    const draftSelects = findElements(draftSection, (n) => n.tagName === "select");
    const draftTypeSelect = draftSelects.find((s) => s.parentElement?.children?.[0]?.textContent === "Provider type");

    draftNewBtn.click();
    assert.equal(draftTestBtn.disabled, false, "Test connection must be enabled for new profile drafts");
    draftTypeSelect.value = "ollama";
    draftTypeSelect.listeners.change?.();

    await draftTestBtn.listeners.click?.();
    assert.ok(testCall, "Test connection must invoke testLlmProfile handler");
    assert.equal(testCall.id, "new", "draft profile id must be new");
    assert.equal(testCall.payload.kind, "ollama", "test payload kind must match selected Provider type");
    assert.equal(testCall.payload.endpoint, "http://127.0.0.1:11434", "test payload endpoint must match selected Provider type");

    // A built-in managed profile is tested by id alone, without a draft payload.
    const managedSection = createLlmProviderSettings({
      profiles: [{ profile_id: "builtin:managed-llama-cpp", name: "managed llama.cpp", kind: "managed_llama_cpp", builtin: true }],
      selection: { primary_profile_id: "builtin:managed-llama-cpp" },
    }, testHandlers);
    testCall = null;
    await findElements(managedSection, (n) => n.tagName === "button" && n.textContent === "Test connection")[0].listeners.click?.();
    assert.deepEqual(testCall, { id: "builtin:managed-llama-cpp", payload: null });
  } finally {
    globalThis.document = previousDocument;
  }
});

