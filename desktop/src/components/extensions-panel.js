import { ACTIVE_RUN_STATUSES, appendRunControls } from "./run-request.js";
import { confirmDestructive } from "./ui/confirm.js";
import { appendText, button, buttonRow, field, labeledValue } from "./ui/dom.js";
import { errorMessage, humanize, isConflict, statusText } from "./ui/format.js";
import { createPanelLifecycle, messageRegion, renderPanelHeader } from "./ui/panel.js";
import { VERB } from "./ui/vocabulary.js";

const FAMILY_TEXT = { mcp: "MCP", acp: "External agent" };

export function extensionStateEnabled(extension, mutationPending) {
  // The backend owns which transitions are legal; the renderer only avoids double-submits
  // and does not resurrect a retired extension it was already told about.
  return Boolean(extension?.extension_id) && !mutationPending && extension.state !== "retired";
}

export function extensionActivityState(extension) {
  if (!extension) return "idle";
  if (extension.state === "retired") return "retired";
  if (extension.state === "disabled") return "blocked";
  if (extension.availability !== "available") return "blocked";
  if (extension.readiness === "degraded") return "degraded";
  return "ready";
}

export function formatExtensionOrigin(extension) {
  if (!extension) return "";
  return `${humanize(extension.family, FAMILY_TEXT)} · ${humanize(extension.trust)} · v${extension.version}`;
}

export function requestedCapabilities(extension) {
  const claims = extension?.metadata_claims?.requested_capabilities;
  return Array.isArray(claims?.ids) ? claims.ids : [];
}

const SAFE_LOCAL_ID = /^[a-z0-9][a-z0-9_.-]*$/;

export function extensionLocalIdValid(localId) {
  return SAFE_LOCAL_ID.test(String(localId || ""));
}

export function isOperatorOwnedProvenance(extension) {
  return String(extension?.provenance || "").startsWith("data/extensions");
}

export function parseAllowlist(text) {
  return String(text || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

// A tool's command is a fixed argv list - each token is its own line so an argument containing
// a comma or space is not mistaken for a separator the way a comma-separated allowlist would.
export function parseCommandLines(text) {
  return String(text || "")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

// extension_runtime_service.py's _mcp wraps every tool/resource/prompt result (everything but
// "discover") as {content: result, trusted: false} before it ever reaches a run record, so the
// MCP SDK's own result shape sits one level under result.content here, not at the top.

// An MCP "get prompt" result is a list of role-tagged messages, not the tool-shaped
// {content: [...]} result every other operation produces - render it as the message text an
// operator actually wants to read rather than the raw JSON block generic results fall back to.
// Any message whose content is not plain text (image, audio, embedded resource) returns null so
// the caller falls back to raw JSON instead of silently dropping that content.
export function formatPromptMessages(result) {
  const messages = result?.content?.messages;
  if (!Array.isArray(messages) || !messages.length) return null;
  const formatted = [];
  for (const message of messages) {
    const text = message?.content?.text;
    if (typeof text !== "string") return null;
    formatted.push({ role: message.role, text });
  }
  return formatted;
}

// An MCP "read resource" result ({contents: [{uri, mimeType, text|blob}]}) is structurally
// distinct from a tool result's {content: [...]} shape and a prompt result's {messages: [...]}
// shape, so this renders it as a content preview - readable text, or an inline image for
// image content - instead of the same raw JSON block a generic result falls back to. Any
// content entry this file has no rendering for (audio, an unrecognized blob type) returns null
// so the caller falls back to raw JSON for the whole result instead of silently dropping it.
export function formatResourceContents(result) {
  const contents = result?.content?.contents;
  if (!Array.isArray(contents) || !contents.length) return null;
  const formatted = [];
  for (const item of contents) {
    const mimeType = String(item?.mimeType || "");
    if (typeof item?.text === "string") {
      formatted.push({ uri: item.uri, mimeType, kind: "text", text: item.text });
    } else if (typeof item?.blob === "string" && mimeType.startsWith("image/")) {
      formatted.push({ uri: item.uri, mimeType, kind: "image", dataUrl: `data:${mimeType};base64,${item.blob}` });
    } else {
      return null;
    }
  }
  return formatted;
}

// "discover" is the one operation name every MCP connection registers, and it is what
// actually contacts the server to refresh health and the discovered tool/resource/prompt
// list - naming it plainly avoids showing a bare, unlabeled schema-derived form for it.
export function operationDisplayName(operation) {
  return operation?.name === "discover" ? "Discover tools and resources" : operation?.name || "";
}

// A discovered MCP operation is named "tool:<name>", "resource:<uri>", or "prompt:<name>" -
// grouping on that prefix is what lets the desktop present them as the separate operator
// concepts they are, instead of one flat list of internal capability names.
const OPERATION_GROUP_PREFIXES = ["tool", "resource", "prompt"];

export function operationKind(operation) {
  const name = String(operation?.name || "");
  if (name === "discover") return "discover";
  const colon = name.indexOf(":");
  if (colon <= 0) return "other";
  const prefix = name.slice(0, colon);
  return OPERATION_GROUP_PREFIXES.includes(prefix) ? prefix : "other";
}

// A tool is invoked, a resource is read (it has no meaningful arguments beyond the URI
// already in its name), and a prompt is fetched with its declared arguments filled in - the
// submit verb should say which of those the operator is about to do, not one generic "Invoke".
export function operationSubmitLabel(operation) {
  const kind = operationKind(operation);
  if (kind === "discover") return "Discover";
  if (kind === "resource") return "Read";
  if (kind === "prompt") return "Get prompt";
  return "Invoke";
}

export function operationShortLabel(operation) {
  const kind = operationKind(operation);
  return OPERATION_GROUP_PREFIXES.includes(kind)
    ? String(operation.name).slice(kind.length + 1)
    : operationDisplayName(operation);
}

export function formatToolResult(result) {
  const content = result?.content?.content;
  if (!Array.isArray(content) || !content.length) return null;
  if (!content.every((item) => item.type === "text" && typeof item.text === "string")) return null;
  return content.map((item) => item.text).join("\n");
}

export function extensionRunTitle(run) {
  const operation = { name: run.operation || "" };
  const label = operationShortLabel(operation);
  return [run.extension_name, label, statusText(run.status || "unknown")]
    .filter(Boolean).join(" · ");
}

function copyState(state) {
  return {
    ...state,
    catalog: state.catalog
      ? { ...state.catalog, extensions: [...(state.catalog.extensions || [])] }
      : null,
    errors: [...state.errors],
    detail: state.detail ? { ...state.detail } : null,
  };
}

export function createExtensionsPanelController(handlers, render = () => undefined) {
  const state = {
    catalog: null,
    errors: [],
    detail: null,
    body: "",
    selectedExtensionId: "",
    familyFilter: "",
    catalogLoading: false,
    errorsLoading: false,
    detailLoading: false,
    mutationPending: false,
    // Invocations still waiting on the backend; their run may already be asking for input.
    invocationsInFlight: 0,
    catalogError: "",
    errorsError: "",
    detailError: "",
    conflict: "",
    notice: "",
    runtime: null,
    runs: [],
    oauth: null,
    oauthStatus: null,
    addConnectionPending: false,
    addConnectionError: "",
    // Read directly by renderAddMcpConnection to decide which field set is visible/required, so
    // a re-render this component did not cause (pending/error state, run polling) reflects the
    // operator's transport choice correctly. A DOM-only toggle driven solely by the <select>'s
    // own "change" listener cannot do this: renderPanel's capture-then-restore mechanism
    // restores a draft-keyed field's .value without dispatching a change event, so a fresh
    // render's hidden/required defaults would never get corrected back after the very re-render
    // that restores the selected transport.
    addConnectionTransport: "streamable_http",
    importSkillPending: false,
    importSkillError: "",
    addToolPending: false,
    addToolError: "",
    addToolFamily: "tool",
    // Which add form, if any, occupies the detail column: "mcp", "skill", "tool", or "acp".
    adding: "",
    definition: null,
    editConnectionPending: false,
    editConnectionError: "",
    editToolPending: false,
    editToolError: "",
  };
  let catalogSequence = 0;
  let errorsSequence = 0;
  let detailSequence = 0;

  function emit() {
    render(copyState(state));
  }

  async function refreshCatalog() {
    if (!handlers.getExtensions) return null;
    const request = ++catalogSequence;
    state.catalogLoading = true;
    state.catalogError = "";
    emit();
    try {
      const payload = await handlers.getExtensions();
      if (request !== catalogSequence) return null;
      state.catalog = payload;
      return payload;
    } catch (error) {
      if (request !== catalogSequence) return null;
      state.catalogError = errorMessage(error, "The extension catalog is unavailable.");
      return null;
    } finally {
      if (request === catalogSequence) {
        state.catalogLoading = false;
        emit();
      }
    }
  }

  async function refreshErrors() {
    if (!handlers.getExtensionErrors) return null;
    const request = ++errorsSequence;
    state.errorsLoading = true;
    state.errorsError = "";
    emit();
    try {
      const payload = await handlers.getExtensionErrors();
      if (request !== errorsSequence) return null;
      state.errors = payload?.errors || [];
      return payload;
    } catch (error) {
      if (request !== errorsSequence) return null;
      state.errorsError = errorMessage(error, "Extension load errors are unavailable.");
      return null;
    } finally {
      if (request === errorsSequence) {
        state.errorsLoading = false;
        emit();
      }
    }
  }

  async function selectExtension(extensionId) {
    if (!handlers.getExtensionDetail) return null;
    const request = ++detailSequence;
    state.selectedExtensionId = extensionId;
    state.adding = "";
    state.detailLoading = true;
    state.detailError = "";
    state.body = "";
    state.definition = null;
    state.editConnectionError = "";
    state.editToolError = "";
    emit();
    try {
      const payload = await handlers.getExtensionDetail(extensionId);
      if (request !== detailSequence) return null;
      state.detail = payload;
      if (handlers.getExtensionRuntime) state.runtime = await handlers.getExtensionRuntime(extensionId);
      if (handlers.getExtensionRuns) state.runs = (await handlers.getExtensionRuns())?.runs || [];
      state.oauth = null;
      state.oauthStatus = null;
      if (handlers.getExtensionOauth && payload?.family === "mcp") {
        try { state.oauthStatus = await handlers.getExtensionOauth(extensionId); } catch { state.oauthStatus = null; }
      }
      return payload;
    } catch (error) {
      if (request !== detailSequence) return null;
      state.detail = null;
      state.detailError = errorMessage(error, "That extension is unavailable.");
      return null;
    } finally {
      if (request === detailSequence) {
        state.detailLoading = false;
        emit();
      }
    }
  }

  async function invoke(extensionId, capabilityId, argumentsValue) {
    state.invocationsInFlight += 1;
    try {
      const result = await handlers.invokeExtension(extensionId, capabilityId, argumentsValue);
      // outcome_unknown means a timeout or cancellation left the backend unable to tell
      // whether the call already ran on the far side - reported distinctly from an
      // ordinary failure so this notice can warn against blindly repeating it, rather
      // than defaulting to the same "Extension invoked." success-sounding text a plain
      // failure would also fall through to otherwise.
      state.notice = result?.status === "awaiting_approval"
        ? "Awaiting approval."
        : result?.status === "outcome_unknown"
        ? "Outcome unknown - the call may already have run; check before repeating it."
        : "Extension invoked.";
      if (handlers.getExtensionRuns) state.runs = (await handlers.getExtensionRuns())?.runs || [];
      // An operation such as MCP "discover" changes the extension's own runtime detail -
      // health, discovered tools/resources/prompts - so a completed invocation must refresh
      // it rather than leave the operator staring at what was true before they clicked.
      if (
        result?.status !== "awaiting_approval"
        && handlers.getExtensionRuntime
        && state.selectedExtensionId === extensionId
      ) {
        try { state.runtime = await handlers.getExtensionRuntime(extensionId); } catch { /* keep the prior runtime display */ }
      }
      emit();
      return result;
    } catch (error) {
      state.detailError = errorMessage(error, "Extension invocation failed.");
      emit();
      return null;
    } finally {
      state.invocationsInFlight -= 1;
    }
  }

  async function answer(runId, requestId, answerValue) {
    try { await handlers.answerExtensionInput(runId, requestId, answerValue); }
    catch (error) { state.detailError = errorMessage(error, "Extension input was not accepted."); emit(); return; }
    if (handlers.getExtensionRuns) state.runs = (await handlers.getExtensionRuns())?.runs || [];
    emit();
  }

  async function credential(extensionId, name, secret) {
    try { await handlers.writeExtensionCredential(extensionId, name, secret); }
    catch (error) { state.detailError = errorMessage(error, "Credential was not stored."); emit(); return; }
    state.notice = "Credential stored.";
    emit();
  }

  async function startOauth(extensionId) {
    if (!handlers.startExtensionOauth) return;
    try {
      const started = await handlers.startExtensionOauth(extensionId);
      state.oauth = { extensionId, state: started?.state || "", url: started?.authorization_url || "" };
      state.notice = "Open the authorization URL, then paste the code below.";
    } catch (error) {
      state.detailError = errorMessage(error, "Authorization could not be started.");
    }
    emit();
  }

  async function completeOauth(extensionId, code) {
    if (!handlers.completeExtensionOauth) return;
    const pending = state.oauth;
    if (!pending || pending.extensionId !== extensionId) {
      state.detailError = "No authorization is in progress for this connection.";
      emit();
      return;
    }
    try {
      await handlers.completeExtensionOauth(extensionId, code, pending.state);
    } catch (error) {
      state.detailError = errorMessage(error, "Authorization was not completed.");
      emit();
      return;
    }
    state.oauth = null;
    state.notice = "Connection authorized.";
    if (handlers.getExtensionOauth) {
      try { state.oauthStatus = await handlers.getExtensionOauth(extensionId); } catch { state.oauthStatus = null; }
    }
    emit();
  }

  async function forgetOauth(extensionId) {
    if (!handlers.forgetExtensionOauth) return;
    let failure = "";
    state.notice = "";
    try {
      await handlers.forgetExtensionOauth(extensionId);
    } catch (error) {
      failure = errorMessage(error, "The stored authorization could not be forgotten.");
    }
    if (state.selectedExtensionId === extensionId) {
      await selectExtension(extensionId);
      state.detailError = failure || state.detailError;
      if (!failure) state.notice = "Stored authorization forgotten.";
    }
    emit();
  }

  async function disconnect(extensionId) {
    if (!handlers.disconnectExtension) return;
    try {
      await handlers.disconnectExtension(extensionId);
    } catch (error) {
      state.detailError = errorMessage(error, "The connection could not be disconnected.");
      emit();
      return;
    }
    state.notice = "Connection disconnected.";
    // Ending the session changes health/discovered-tools display the same way an
    // invocation does, so refresh the same way invoke() does after one completes.
    if (handlers.getExtensionRuntime && state.selectedExtensionId === extensionId) {
      try { state.runtime = await handlers.getExtensionRuntime(extensionId); } catch { /* keep the prior runtime display */ }
    }
    emit();
  }

  async function importSkill(localId, body) {
    if (!handlers.proposeAction || state.importSkillPending) return null;
    if (!extensionLocalIdValid(localId)) {
      state.importSkillError = "Skill ID must start with a letter or digit and use only lowercase letters, digits, '_', '.', or '-'.";
      emit();
      return null;
    }
    state.importSkillPending = true;
    state.importSkillError = "";
    emit();
    try {
      const result = await handlers.proposeAction({
        capabilityId: "extension-skill-write",
        actionArguments: { local_id: localId, body },
        reason: `Import operator skill ${localId}`,
        proposedBy: "operator",
      });
      if (result?.status !== "success") {
        state.importSkillError = result?.execution?.error || "The skill was not imported.";
        return null;
      }
      state.notice = "Skill imported.";
      state.adding = "";
      await refreshCatalog();
      return true;
    } catch (error) {
      state.importSkillError = errorMessage(error, "The skill was not imported.");
      return null;
    } finally {
      state.importSkillPending = false;
      emit();
    }
  }

  async function saveSkill(localId, body) {
    if (!handlers.proposeAction) return;
    try {
      const result = await handlers.proposeAction({
        capabilityId: "extension-skill-write",
        actionArguments: { local_id: localId, body },
        reason: `Save operator skill ${localId}`,
        proposedBy: "operator",
      });
      if (result?.status !== "success") {
        state.detailError = result?.execution?.error || "The skill was not saved.";
        emit();
        return;
      }
    } catch (error) {
      state.detailError = errorMessage(error, "The skill was not saved.");
      emit();
      return;
    }
    state.notice = "Skill saved.";
    await refreshCatalog();
    emit();
  }

  async function removeSkill(localId) {
    if (!handlers.proposeAction) return;
    let result;
    try {
      result = await handlers.proposeAction({
        capabilityId: "extension-skill-delete",
        actionArguments: { local_id: localId },
        reason: `Remove operator skill ${localId}`,
        proposedBy: "operator",
      });
    } catch (error) {
      state.detailError = errorMessage(error, "The skill was not removed.");
      emit();
      return;
    }
    if (result?.status !== "success") {
      state.detailError = result?.execution?.error || "The skill was not removed.";
      emit();
      return;
    }
    state.notice = "Skill removed.";
    state.detail = null;
    state.selectedExtensionId = "";
    await refreshCatalog();
    emit();
  }

  // `base` carries forward any field the add/edit form does not know about - so saving a
  // display-name or allowlist change cannot silently erase something the form does not expose.
  // Add passes an empty base (nothing to preserve yet); an edit passes the just-loaded
  // definition. An empty allowlist/reference means "no restriction"/"none configured" on the
  // backend, so it is omitted rather than sent as an empty value - an operator who leaves these
  // blank gets an unrestricted connection, not one that can reach nothing. Explicit delete (not
  // skip) so clearing a previously-set value on an edit actually clears it instead of leaving
  // the preserved base value in place.
  function applyMcpAllowlists(definition, { toolAllowlist, resourceAllowlist, promptAllowlist }) {
    const tools = parseAllowlist(toolAllowlist);
    const resources = parseAllowlist(resourceAllowlist);
    const prompts = parseAllowlist(promptAllowlist);
    if (tools.length) definition.tool_allowlist = tools; else delete definition.tool_allowlist;
    if (resources.length) definition.resource_allowlist = resources; else delete definition.resource_allowlist;
    if (prompts.length) definition.prompt_allowlist = prompts; else delete definition.prompt_allowlist;
  }

  // credential_ref is a reference name into the operator secret store, never the secret itself -
  // the secret is stored only through the dedicated Store credential route. Returns the trimmed
  // reference so stdioDefinition can also fold it into env_passthrough.
  function applyMcpCredentialRef(definition, credentialRef) {
    const ref = String(credentialRef || "").trim();
    if (ref) definition.credential_ref = ref; else delete definition.credential_ref;
    return ref;
  }

  function streamableHttpDefinition(base, {
    url, toolAllowlist, resourceAllowlist, promptAllowlist, credentialRef, oauth,
  }) {
    const definition = { ...base, transport: "streamable_http", url };
    delete definition.command;
    delete definition.process;
    applyMcpAllowlists(definition, { toolAllowlist, resourceAllowlist, promptAllowlist });
    applyMcpCredentialRef(definition, credentialRef);
    const oauthConfig = buildOauthConfig(oauth);
    if (oauthConfig) definition.oauth = oauthConfig; else delete definition.oauth;
    return definition;
  }

  // A stdio connection's credential_ref only reaches the child process if it is also
  // allowlisted in env_passthrough (ProcessBoundary.scrub_environment is an allowlist, not a
  // wildcard) - McpConnectionRuntime's mcp_credentials() refuses the connection otherwise, so
  // the reference is added to env_passthrough automatically rather than leaving the operator to
  // discover that coupling from a runtime refusal. OAuth is not a stdio field: MCP's OAuth
  // authorization-code flow targets an HTTP-reachable server, and McpConnectionDefinition
  // itself forbids a stdio connection from declaring a url for OAuth to discover endpoints
  // against, so transport is not switchable in place - it is fixed at create time.
  function stdioDefinition(base, {
    command, argvAllowlist, envPassthrough, workingRoot, toolAllowlist, resourceAllowlist, promptAllowlist, credentialRef,
  }) {
    const definition = { ...base, transport: "stdio", command: parseCommandLines(command) };
    delete definition.url;
    delete definition.oauth;
    applyMcpAllowlists(definition, { toolAllowlist, resourceAllowlist, promptAllowlist });
    const ref = applyMcpCredentialRef(definition, credentialRef);
    const envList = parseAllowlist(envPassthrough);
    if (ref && !envList.includes(ref)) envList.push(ref);
    definition.process = {
      // Every stdio MCP connection registers with effect_class "privileged_execution"
      // (extension_runtime_service.py's _operations_for), and boundaries.py rejects a
      // privileged_execution capability whose process boundary declares subprocess: false -
      // the same fixed fact Add/Edit Local Tool already established for its own process field.
      subprocess: true,
      argv_allowlist: parseAllowlist(argvAllowlist),
      env_passthrough: envList,
      working_root: workingRoot,
    };
    return definition;
  }

  // Only client_id is required to configure OAuth at all; authorization_url and token_url are
  // optional together (McpConnectionDefinition discovers them from the server's
  // protected-resource metadata when both are omitted) but the backend refuses one without the
  // other, so this leaves that pairing to the backend's own refusal rather than duplicating the
  // rule client-side. Leaving client_id blank means "no OAuth configured," matching an absent
  // oauth block; client_secret is never a form field, since an inline secret is refused by
  // discovery.py's secret-key check and must go through the credential-reference/store path.
  function buildOauthConfig({ clientId, authorizationUrl, tokenUrl, scopes, redirectPort, resource } = {}) {
    const client = String(clientId || "").trim();
    if (!client) return null;
    const config = { client_id: client };
    const authorization = String(authorizationUrl || "").trim();
    const token = String(tokenUrl || "").trim();
    if (authorization) config.authorization_url = authorization;
    if (token) config.token_url = token;
    const scopeList = parseAllowlist(scopes);
    if (scopeList.length) config.scopes = scopeList;
    const port = Number(redirectPort);
    if (String(redirectPort || "").trim() && Number.isFinite(port)) config.redirect_port = port;
    const resourceUrl = String(resource || "").trim();
    if (resourceUrl) config.resource = resourceUrl;
    return config;
  }

  function buildMcpDefinition(base, transport, fields) {
    return transport === "stdio" ? stdioDefinition(base, fields) : streamableHttpDefinition(base, fields);
  }

  async function addMcpConnection({
    localId, name, transport, url, toolAllowlist, resourceAllowlist, promptAllowlist, credentialRef, oauth,
    command, argvAllowlist, envPassthrough, workingRoot,
  }) {
    if (!handlers.proposeAction || state.addConnectionPending) return null;
    if (!extensionLocalIdValid(localId)) {
      state.addConnectionError = "Connection ID must start with a letter or digit and use only lowercase letters, digits, '_', '.', or '-'.";
      emit();
      return null;
    }
    state.addConnectionPending = true;
    state.addConnectionError = "";
    emit();
    try {
      const result = await handlers.proposeAction({
        capabilityId: "extension-definition-write",
        actionArguments: {
          family: "mcp",
          local_id: localId,
          name,
          version: "1.0.0",
          definition: buildMcpDefinition({}, transport, {
            url, toolAllowlist, resourceAllowlist, promptAllowlist, credentialRef, oauth,
            command, argvAllowlist, envPassthrough, workingRoot,
          }),
        },
        reason: `Add MCP connection ${name}`,
        proposedBy: "operator",
      });
      if (result?.status !== "success") {
        state.addConnectionError = result?.execution?.error || "The connection was not added.";
        return null;
      }
      state.notice = "MCP connection added.";
      state.adding = "";
      await refreshCatalog();
      return true;
    } catch (error) {
      state.addConnectionError = errorMessage(error, "The connection was not added.");
      return null;
    } finally {
      state.addConnectionPending = false;
      emit();
    }
  }

  async function updateMcpConnection({
    localId, name, url, toolAllowlist, resourceAllowlist, promptAllowlist, credentialRef, oauth,
    command, argvAllowlist, envPassthrough, workingRoot,
  }) {
    if (!handlers.proposeAction || state.editConnectionPending || !state.definition) return null;
    state.editConnectionPending = true;
    state.editConnectionError = "";
    emit();
    try {
      // Transport is not an edit-form field - it is fixed to whatever the loaded definition
      // already declares, since switching transport in place is not a supported edit.
      const transport = state.definition.definition.transport;
      const result = await handlers.proposeAction({
        capabilityId: "extension-definition-write",
        actionArguments: {
          family: "mcp",
          local_id: localId,
          name,
          version: state.definition.version,
          definition: buildMcpDefinition(state.definition.definition, transport, {
            url, toolAllowlist, resourceAllowlist, promptAllowlist, credentialRef, oauth,
            command, argvAllowlist, envPassthrough, workingRoot,
          }),
          dependencies: state.definition.dependencies,
          metadata: state.definition.metadata,
          enabled: state.definition.enabled,
          expected_fingerprint: state.definition.fingerprint,
        },
        reason: `Update MCP connection ${name}`,
        proposedBy: "operator",
      });
      if (result?.status !== "success") {
        state.editConnectionError = result?.execution?.error || "The connection was not saved.";
        return null;
      }
      state.notice = "MCP connection saved.";
      state.definition = null;
      await refreshCatalog();
      await selectExtension(`mcp:${localId}`);
      return true;
    } catch (error) {
      state.editConnectionError = errorMessage(error, "The connection was not saved.");
      return null;
    } finally {
      state.editConnectionPending = false;
      emit();
    }
  }

  async function removeMcpConnection(localId) {
    if (!handlers.proposeAction) return;
    let result;
    try {
      result = await handlers.proposeAction({
        capabilityId: "extension-definition-delete",
        actionArguments: { family: "mcp", local_id: localId },
        reason: `Remove MCP connection ${localId}`,
        proposedBy: "operator",
      });
    } catch (error) {
      state.detailError = errorMessage(error, "The connection was not removed.");
      emit();
      return;
    }
    if (result?.status !== "success") {
      state.detailError = result?.execution?.error || "The connection was not removed.";
      emit();
      return;
    }
    state.notice = "MCP connection removed.";
    state.detail = null;
    state.selectedExtensionId = "";
    await refreshCatalog();
    emit();
  }

  // `base` carries forward any field the add/edit form does not know about - `skill_id` and
  // `script`, which make a tool run a skill's declared script rather than an arbitrary command
  // - so saving a command or allowlist change cannot silently detach it from its skill. Add
  // passes an empty base (nothing to preserve yet); an edit passes the just-loaded definition.
  function toolDefinition(base, { command, argvAllowlist, envPassthrough, workingRoot }) {
    return {
      ...base,
      command: parseCommandLines(command),
      process: {
        // A tool always registers with effect_class "privileged_execution"
        // (backend/app/services/extension_runtime_service.py), and boundaries.py
        // rejects a privileged_execution capability whose process boundary declares
        // subprocess: false - so this is not an operator choice, only a fixed fact.
        subprocess: true,
        argv_allowlist: parseAllowlist(argvAllowlist),
        env_passthrough: parseAllowlist(envPassthrough),
        working_root: workingRoot,
      },
    };
  }

  async function addLocalTool({ family = "tool", localId, name, command, argvAllowlist, envPassthrough, workingRoot }) {
    if (!handlers.proposeAction || state.addToolPending) return null;
    const labels = COMMAND_FAMILIES[family];
    state.addToolFamily = family;
    if (!extensionLocalIdValid(localId)) {
      state.addToolError = `${labels.idLabel} must start with a letter or digit and use only lowercase letters, digits, '_', '.', or '-'.`;
      emit();
      return null;
    }
    state.addToolPending = true;
    state.addToolError = "";
    emit();
    try {
      const result = await handlers.proposeAction({
        capabilityId: "extension-definition-write",
        actionArguments: {
          family,
          local_id: localId,
          name,
          version: "1.0.0",
          definition: toolDefinition({}, { command, argvAllowlist, envPassthrough, workingRoot }),
        },
        reason: `Add ${labels.title} ${name}`,
        proposedBy: "operator",
      });
      if (result?.status !== "success") {
        state.addToolError = result?.execution?.error || `The ${labels.noun} was not added.`;
        return null;
      }
      state.notice = `${labels.heading} added.`;
      state.adding = "";
      await refreshCatalog();
      return true;
    } catch (error) {
      state.addToolError = errorMessage(error, `The ${labels.noun} was not added.`);
      return null;
    } finally {
      state.addToolPending = false;
      emit();
    }
  }

  async function updateLocalTool({ family = "tool", localId, name, command, argvAllowlist, envPassthrough, workingRoot }) {
    if (!handlers.proposeAction || state.editToolPending || !state.definition) return null;
    const labels = COMMAND_FAMILIES[family];
    state.editToolPending = true;
    state.editToolError = "";
    emit();
    try {
      const result = await handlers.proposeAction({
        capabilityId: "extension-definition-write",
        actionArguments: {
          family,
          local_id: localId,
          name,
          version: state.definition.version,
          definition: toolDefinition(state.definition.definition, { command, argvAllowlist, envPassthrough, workingRoot }),
          dependencies: state.definition.dependencies,
          metadata: state.definition.metadata,
          enabled: state.definition.enabled,
          expected_fingerprint: state.definition.fingerprint,
        },
        reason: `Update ${labels.title} ${name}`,
        proposedBy: "operator",
      });
      if (result?.status !== "success") {
        state.editToolError = result?.execution?.error || `The ${labels.noun} was not saved.`;
        return null;
      }
      state.notice = `${labels.heading} saved.`;
      state.definition = null;
      await refreshCatalog();
      await selectExtension(`${family}:${localId}`);
      return true;
    } catch (error) {
      state.editToolError = errorMessage(error, `The ${labels.noun} was not saved.`);
      return null;
    } finally {
      state.editToolPending = false;
      emit();
    }
  }

  async function removeLocalTool(localId, family = "tool") {
    if (!handlers.proposeAction) return;
    const labels = COMMAND_FAMILIES[family];
    let result;
    try {
      result = await handlers.proposeAction({
        capabilityId: "extension-definition-delete",
        actionArguments: { family, local_id: localId },
        reason: `Remove ${labels.title} ${localId}`,
        proposedBy: "operator",
      });
    } catch (error) {
      state.detailError = errorMessage(error, `The ${labels.noun} was not removed.`);
      emit();
      return;
    }
    if (result?.status !== "success") {
      state.detailError = result?.execution?.error || `The ${labels.noun} was not removed.`;
      emit();
      return;
    }
    state.notice = `${labels.heading} removed.`;
    state.detail = null;
    state.selectedExtensionId = "";
    await refreshCatalog();
    emit();
  }

  async function refreshRuns() {
    if (!handlers.getExtensionRuns) return;
    state.runs = (await handlers.getExtensionRuns())?.runs || [];
    emit();
  }

  async function decide(proposalId, outcome) {
    try {
      await handlers.decideAction(proposalId, outcome);
    } catch (error) {
      state.detailError = errorMessage(error, "That decision was not applied.");
    }
    await refreshRuns();
    // An approval-gated run (every stdio MCP "discover", any other privileged_execution
    // operation) resolves here, outside invoke()'s own post-invocation refresh above - without
    // this, an approved discover's tools/resources/prompts never reach the operator until they
    // navigate away from the extension and back, even though the run itself already shows
    // success.
    const run = state.runs.find((item) => item.proposal_id === proposalId);
    if (run?.extension_id === state.selectedExtensionId && handlers.getExtensionRuntime) {
      try { state.runtime = await handlers.getExtensionRuntime(state.selectedExtensionId); } catch { /* keep the prior runtime display */ }
      emit();
    }
  }

  async function cancel(proposalId, confirmCancel) {
    // Cancelling a run is not reversible, so it is confirmed the way the actions panel
    // confirms its own cancellations.
    const confirmed = confirmCancel ? await confirmCancel("Cancel this run?") : true;
    if (!confirmed) return;
    try {
      await handlers.cancelAction(proposalId);
    } catch (error) {
      state.detailError = errorMessage(error, "The run could not be cancelled.");
    }
    await refreshRuns();
  }

  async function loadBody(extensionId) {
    if (!handlers.getExtensionBody) return null;
    const request = detailSequence;
    try {
      const payload = await handlers.getExtensionBody(extensionId);
      if (request !== detailSequence) return null;
      state.body = payload?.body || "";
      return payload;
    } catch (error) {
      if (request !== detailSequence) return null;
      state.detailError = errorMessage(error, "That extension has no readable body.");
      return null;
    } finally {
      if (request === detailSequence) emit();
    }
  }

  function cancelDefinitionEdit() {
    state.definition = null;
    state.editConnectionError = "";
    state.editToolError = "";
    emit();
  }

  function setAddConnectionTransport(transport) {
    state.addConnectionTransport = transport === "stdio" ? "stdio" : "streamable_http";
    emit();
  }

  async function loadDefinition(extensionId) {
    if (!handlers.getExtensionDefinition) return null;
    const request = detailSequence;
    try {
      const payload = await handlers.getExtensionDefinition(extensionId);
      if (request !== detailSequence) return null;
      state.definition = payload;
      return payload;
    } catch (error) {
      if (request !== detailSequence) return null;
      state.detailError = errorMessage(error, "That definition is not readable.");
      return null;
    } finally {
      if (request === detailSequence) emit();
    }
  }

  async function setState(extensionId, nextState, reason = null) {
    if (state.mutationPending) return null;
    state.mutationPending = true;
    state.conflict = "";
    state.notice = "";
    state.detailError = "";
    emit();
    try {
      const current = state.detail?.revision ?? null;
      const payload = await handlers.setExtensionState(extensionId, nextState, current, reason);
      state.detail = payload;
      state.notice = `Extension ${nextState}.`;
      await refreshCatalog();
      return payload;
    } catch (error) {
      if (isConflict(error)) {
        state.conflict = `${errorMessage(error, "That change was not applied.")} The extension was reloaded.`;
      } else {
        state.detailError = errorMessage(error, "That extension could not be changed.");
      }
      await refreshCatalog();
      await selectExtension(extensionId);
      return null;
    } finally {
      state.mutationPending = false;
      emit();
    }
  }

  function filterFamily(family) {
    state.familyFilter = family;
    emit();
  }

  function startAdd(kind) {
    state.adding = kind;
    state.addConnectionError = "";
    state.addToolError = "";
    state.importSkillError = "";
    emit();
  }

  function cancelAdd() {
    state.adding = "";
    emit();
  }

  function notice(message) {
    state.notice = message;
    emit();
  }

  async function load() {
    await Promise.all([refreshCatalog(), refreshErrors()]);
  }

  function cancelPendingReads() {
    catalogSequence += 1;
    errorsSequence += 1;
    detailSequence += 1;
    state.catalogLoading = false;
    state.errorsLoading = false;
    state.detailLoading = false;
  }

  emit();
  return {
    load,
    refreshCatalog,
    refreshErrors,
    selectExtension,
    loadBody,
    loadDefinition,
    cancelDefinitionEdit,
    setAddConnectionTransport,
    setState,
    filterFamily,
    startAdd,
    cancelAdd,
    invoke,
    answer,
    credential,
    importSkill,
    saveSkill,
    removeSkill,
    addMcpConnection,
    updateMcpConnection,
    removeMcpConnection,
    addLocalTool,
    updateLocalTool,
    removeLocalTool,
    startOauth,
    completeOauth,
    forgetOauth,
    disconnect,
    refreshRuns,
    decide,
    cancel,
    notice,
    cancelPendingReads,
    snapshot: () => copyState(state),
  };
}

export function formatRunStarted(startedAt) {
  if (!startedAt) return "—";
  const date = new Date(startedAt);
  return Number.isNaN(date.getTime()) ? String(startedAt) : date.toLocaleTimeString();
}

// The command and process boundary fields shared by stdio MCP connections, local tools, and
// external agents.
function processFields({ command, argvAllowlist, envPassthrough, workingRoot }) {
  return [
    field("Command", command),
    field("Allowed executables", argvAllowlist),
    field("Environment passthrough", envPassthrough),
    field("Working root", workingRoot),
  ];
}

function renderCancelAdd(state) {
  return button(VERB.discard, {
    onClick: () => state.actions.cancelAdd(),
  });
}

// Shared by every MCP connection field set (Add/Edit, streamable_http/stdio) so `credential_ref`
// - a plain reference name into the operator secret store, never the secret itself, which is
// stored only through the separate Store credential form - is declared once.
function appendCredentialRefField(form, prefix, value = "") {
  const credentialRef = document.createElement("input");
  credentialRef.placeholder = "Optional, e.g. weather-api-key";
  credentialRef.dataset.draftKey = `${prefix}:credential-ref`;
  credentialRef.value = value || "";
  form.appendChild(field("Credential reference", credentialRef));
  return credentialRef;
}

// OAuth is a streamable_http-only field set: MCP's OAuth authorization-code flow targets an
// HTTP-reachable server, and McpConnectionDefinition itself forbids a stdio connection from
// declaring the url an OAuth flow would discover endpoints against. Fields match
// McpConnectionDefinition._validate_oauth's contract exactly - client_id is the only required
// field, authorization_url/token_url are optional together (the backend discovers them from the
// server when both are blank), and client_secret is deliberately not a field here since an
// inline secret is refused before it reaches disk.
function appendOauthFieldset(form, prefix, oauth = {}) {
  const oauthClientId = document.createElement("input");
  oauthClientId.placeholder = "Optional";
  oauthClientId.dataset.draftKey = `${prefix}:oauth-client-id`;
  oauthClientId.value = oauth.client_id || "";
  const oauthAuthorizationUrl = document.createElement("input");
  oauthAuthorizationUrl.type = "url";
  oauthAuthorizationUrl.placeholder = "Optional, discovered if blank";
  oauthAuthorizationUrl.dataset.draftKey = `${prefix}:oauth-authorization-url`;
  oauthAuthorizationUrl.value = oauth.authorization_url || "";
  const oauthTokenUrl = document.createElement("input");
  oauthTokenUrl.type = "url";
  oauthTokenUrl.placeholder = "Optional, discovered if blank";
  oauthTokenUrl.dataset.draftKey = `${prefix}:oauth-token-url`;
  oauthTokenUrl.value = oauth.token_url || "";
  const oauthScopes = document.createElement("input");
  oauthScopes.placeholder = "Comma-separated, optional";
  oauthScopes.dataset.draftKey = `${prefix}:oauth-scopes`;
  oauthScopes.value = (oauth.scopes || []).join(", ");
  const oauthRedirectPort = document.createElement("input");
  oauthRedirectPort.type = "number";
  oauthRedirectPort.placeholder = "Optional, default 19823";
  oauthRedirectPort.dataset.draftKey = `${prefix}:oauth-redirect-port`;
  oauthRedirectPort.value = oauth.redirect_port != null ? String(oauth.redirect_port) : "";
  const oauthResource = document.createElement("input");
  oauthResource.type = "url";
  oauthResource.placeholder = "Optional";
  oauthResource.dataset.draftKey = `${prefix}:oauth-resource`;
  oauthResource.value = oauth.resource || "";
  const oauthFields = document.createElement("fieldset");
  appendText(oauthFields, "OAuth (optional)", "legend");
  oauthFields.append(
    field("Client ID", oauthClientId),
    field("Authorization URL", oauthAuthorizationUrl),
    field("Token URL", oauthTokenUrl),
    field("Scopes", oauthScopes),
    field("Redirect port", oauthRedirectPort),
    field("Resource URL", oauthResource),
  );
  form.appendChild(oauthFields);
  return {
    oauthClientId, oauthAuthorizationUrl, oauthTokenUrl,
    oauthScopes, oauthRedirectPort, oauthResource,
  };
}

function collectOauthFromFields(fields) {
  return {
    clientId: fields.oauthClientId.value.trim(),
    authorizationUrl: fields.oauthAuthorizationUrl.value.trim(),
    tokenUrl: fields.oauthTokenUrl.value.trim(),
    scopes: fields.oauthScopes.value,
    redirectPort: fields.oauthRedirectPort.value.trim(),
    resource: fields.oauthResource.value.trim(),
  };
}

function renderAddMcpConnection(state) {
  const form = document.createElement("form");
  form.className = "extensions-add-connection";
  appendText(form, "Add MCP connection", "strong");
  const name = document.createElement("input");
    name.required = true;
  name.dataset.draftKey = "add-mcp:name";
  const localId = document.createElement("input");
  localId.placeholder = "e.g. weather";
  localId.required = true;
  localId.dataset.draftKey = "add-mcp:local-id";
  // Visibility/required state is derived from state.addConnectionTransport, not from the
  // <select>'s own live value, and the change listener below writes to that state (through
  // setAddConnectionTransport) rather than toggling the DOM directly. A re-render this form did
  // not cause - pending/error state, run polling - rebuilds these elements from scratch with
  // fresh hidden/required defaults; renderPanel's capture-then-restore mechanism would then
  // restore the <select>'s .value to the operator's chosen transport without dispatching a
  // change event, so a DOM-only toggle would leave the wrong field set visible and required
  // after every such render. Deriving from real controller state instead means the correct
  // field set is right the first time, on every render, with nothing to resynchronize.
  const isStdio = state.addConnectionTransport === "stdio";
  const transport = document.createElement("select");
  for (const [value, text] of [["streamable_http", "HTTP server"], ["stdio", "Local process (stdio)"]]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    transport.appendChild(option);
  }
  transport.value = state.addConnectionTransport;
  transport.addEventListener("change", () => state.actions.setAddConnectionTransport(transport.value));
  form.append(field("Name", name), field("Connection ID", localId), field("Transport", transport));

  const httpFields = document.createElement("div");
  httpFields.hidden = isStdio;
  const url = document.createElement("input");
  url.type = "url";
  url.placeholder = "https://server.example/mcp";
  url.required = !isStdio;
  url.dataset.draftKey = "add-mcp:url";
  httpFields.appendChild(field("Server URL", url));
  const oauthFields = appendOauthFieldset(httpFields, "add-mcp");
  form.appendChild(httpFields);

  const stdioFields = document.createElement("div");
  stdioFields.hidden = !isStdio;
  const command = document.createElement("textarea");
  command.placeholder = "One argv token per line, e.g.\npython3\n-m\nmymcp.server";
  command.required = isStdio;
  command.dataset.draftKey = "add-mcp:command";
  const argvAllowlist = document.createElement("input");
  argvAllowlist.placeholder = "Comma-separated, e.g. python3";
  argvAllowlist.required = isStdio;
  argvAllowlist.dataset.draftKey = "add-mcp:argv-allowlist";
  const envPassthrough = document.createElement("input");
  envPassthrough.placeholder = "Comma-separated, optional";
  envPassthrough.dataset.draftKey = "add-mcp:env-passthrough";
  const workingRoot = document.createElement("select");
  workingRoot.dataset.draftKey = "add-mcp:working-root";
  for (const root of STORAGE_ROOTS) {
    const option = document.createElement("option");
    option.value = root;
    option.textContent = root;
    workingRoot.appendChild(option);
  }
  stdioFields.append(...processFields({ command, argvAllowlist, envPassthrough, workingRoot }));
  form.appendChild(stdioFields);

  const toolAllowlist = document.createElement("input");
  toolAllowlist.placeholder = "Comma-separated, optional";
  toolAllowlist.dataset.draftKey = "add-mcp:tool-allowlist";
  const resourceAllowlist = document.createElement("input");
  resourceAllowlist.placeholder = "Comma-separated, optional";
  resourceAllowlist.dataset.draftKey = "add-mcp:resource-allowlist";
  const promptAllowlist = document.createElement("input");
  promptAllowlist.placeholder = "Comma-separated, optional";
  promptAllowlist.dataset.draftKey = "add-mcp:prompt-allowlist";
  form.append(field("Allowed tools", toolAllowlist), field("Allowed resources", resourceAllowlist), field("Allowed prompts", promptAllowlist));
  const credentialRef = appendCredentialRefField(form, "add-mcp");
  const submit = button("Add connection", {
    type: "submit",
    variant: "primary",
    disabled: state.addConnectionPending,
    focusKey: "add-mcp:submit",
  });
  form.appendChild(buttonRow(submit, renderCancelAdd(state)));
  if (state.addConnectionError) appendText(form, state.addConnectionError, "p", "extensions-error");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const shared = {
      localId: localId.value.trim(),
      name: name.value.trim(),
      toolAllowlist: toolAllowlist.value,
      resourceAllowlist: resourceAllowlist.value,
      promptAllowlist: promptAllowlist.value,
      credentialRef: credentialRef.value.trim(),
    };
    if (isStdio) {
      state.actions.addMcpConnection({
        ...shared,
        transport: "stdio",
        command: command.value,
        argvAllowlist: argvAllowlist.value,
        envPassthrough: envPassthrough.value,
        workingRoot: workingRoot.value,
      });
    } else {
      state.actions.addMcpConnection({
        ...shared,
        transport: "streamable_http",
        url: url.value.trim(),
        oauth: collectOauthFromFields(oauthFields),
      });
    }
  });
  return form;
}

function renderImportSkill(state) {
  const form = document.createElement("form");
  form.className = "extensions-import-skill";
  appendText(form, "Import skill", "strong");
  const localId = document.createElement("input");
  localId.placeholder = "e.g. changelog-writer";
  localId.required = true;
  localId.dataset.draftKey = "import-skill:local-id";
  const body = document.createElement("textarea");
  body.placeholder = "---\nname: Changelog Writer\n---\nInstructions go here.";
  body.required = true;
  body.dataset.draftKey = "import-skill:body";
  const submit = button("Import skill", {
    type: "submit",
    variant: "primary",
    disabled: state.importSkillPending,
    focusKey: "import-skill:submit",
  });
  form.append(field("Skill ID", localId), field("Skill file", body), buttonRow(submit, renderCancelAdd(state)));
  if (state.importSkillError) appendText(form, state.importSkillError, "p", "extensions-error");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    state.actions.importSkill(localId.value.trim(), body.value);
  });
  return form;
}

const ADD_FORMS = [
  ["mcp", "Add MCP connection"],
  ["skill", "Import skill"],
  ["tool", "Add local tool"],
  ["acp", "Add external agent"],
];

function renderAddForm(state) {
  const section = document.createElement("section");
  section.className = "extensions-section";
  const form = state.adding === "mcp"
    ? renderAddMcpConnection(state)
    : state.adding === "skill"
      ? renderImportSkill(state)
      : renderAddLocalTool(state, state.adding);
  section.appendChild(form);
  return section;
}

const STORAGE_ROOTS = ["data", "cache", "reports", "models", "runtimes"];

// Local tools and external (ACP) agents are both declared as a fixed argv command plus a process
// boundary, so they share one add/edit/remove workflow and differ only in wording.
const COMMAND_FAMILIES = {
  tool: {
    noun: "tool",
    title: "local tool",
    heading: "Local tool",
    idLabel: "Tool ID",
    idExample: "changelog-writer",
    commandExample: "python3\n-m\nscripts.changelog",
    allowExample: "python3",
  },
  acp: {
    noun: "agent",
    title: "external agent",
    heading: "External agent",
    idLabel: "Agent ID",
    idExample: "coding-agent",
    commandExample: "npx\n-y\nexample-acp-agent",
    allowExample: "npx",
  },
};

function renderAddLocalTool(state, family = "tool") {
  const labels = COMMAND_FAMILIES[family];
  const form = document.createElement("form");
  form.className = `extensions-add-${family}`;
  appendText(form, `Add ${labels.title}`, "strong");
  const name = document.createElement("input");
    name.required = true;
  name.dataset.draftKey = `add-${family}:name`;
  const localId = document.createElement("input");
  localId.placeholder = `e.g. ${labels.idExample}`;
  localId.required = true;
  localId.dataset.draftKey = `add-${family}:local-id`;
  const command = document.createElement("textarea");
  command.placeholder = `One argv token per line, e.g.\n${labels.commandExample}`;
  command.required = true;
  command.dataset.draftKey = `add-${family}:command`;
  const argvAllowlist = document.createElement("input");
  argvAllowlist.placeholder = `Comma-separated, e.g. ${labels.allowExample}`;
  argvAllowlist.required = true;
  argvAllowlist.dataset.draftKey = `add-${family}:argv-allowlist`;
  const envPassthrough = document.createElement("input");
  envPassthrough.placeholder = "Comma-separated, optional";
  envPassthrough.dataset.draftKey = `add-${family}:env-passthrough`;
  const workingRoot = document.createElement("select");
  workingRoot.dataset.draftKey = `add-${family}:working-root`;
  for (const root of STORAGE_ROOTS) {
    const option = document.createElement("option");
    option.value = root;
    option.textContent = root;
    workingRoot.appendChild(option);
  }
  const submit = button(`Add ${labels.noun}`, {
    type: "submit",
    variant: "primary",
    disabled: state.addToolPending,
    focusKey: `add-${family}:submit`,
  });
  form.append(
    field("Name", name),
    field(labels.idLabel, localId),
    ...processFields({ command, argvAllowlist, envPassthrough, workingRoot }),
    buttonRow(submit, renderCancelAdd(state)),
  );
  if (state.addToolError && state.addToolFamily === family) appendText(form, state.addToolError, "p", "extensions-error");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    state.actions.addLocalTool({
      family,
      localId: localId.value.trim(),
      name: name.value.trim(),
      command: command.value,
      argvAllowlist: argvAllowlist.value,
      envPassthrough: envPassthrough.value,
      workingRoot: workingRoot.value,
    });
  });
  return form;
}

function renderCancelEdit(state, focusKey) {
  return button("Cancel edit", {
    focusKey,
    onClick: () => state.actions.cancelDefinitionEdit(),
  });
}

// Rendered only once a definition has actually loaded, so unlike a form that renders
// unconditionally before its content exists, there is no stale draft-key entry from a prior
// (empty) render for the capture-then-restore mechanism to reapply over the freshly seeded
// values - the same hazard fixed in the Edit skill editor does not apply here.
function renderEditMcpConnection(state) {
  const info = state.definition;
  const isStdio = info.definition.transport === "stdio";
  const form = document.createElement("form");
  form.className = "extensions-edit-connection";
  appendText(form, "Edit MCP connection", "strong");
  const name = document.createElement("input");
    name.required = true;
  name.dataset.draftKey = `edit-mcp:${info.extension_id}:name`;
  name.value = info.name;
  form.appendChild(field("Name", name));

  let url = null;
  let oauthFields = null;
  let command = null;
  let argvAllowlist = null;
  let envPassthrough = null;
  let workingRoot = null;
  if (isStdio) {
    command = document.createElement("textarea");
    command.placeholder = "One argv token per line";
    command.required = true;
    command.dataset.draftKey = `edit-mcp:${info.extension_id}:command`;
    command.value = (info.definition.command || []).join("\n");
    argvAllowlist = document.createElement("input");
    argvAllowlist.placeholder = "Comma-separated, e.g. python3";
    argvAllowlist.required = true;
    argvAllowlist.dataset.draftKey = `edit-mcp:${info.extension_id}:argv-allowlist`;
    argvAllowlist.value = (info.definition.process?.argv_allowlist || []).join(", ");
    envPassthrough = document.createElement("input");
    envPassthrough.placeholder = "Comma-separated, optional";
    envPassthrough.dataset.draftKey = `edit-mcp:${info.extension_id}:env-passthrough`;
    envPassthrough.value = (info.definition.process?.env_passthrough || []).join(", ");
    workingRoot = document.createElement("select");
    workingRoot.dataset.draftKey = `edit-mcp:${info.extension_id}:working-root`;
    for (const root of STORAGE_ROOTS) {
      const option = document.createElement("option");
      option.value = root;
      option.textContent = root;
      workingRoot.appendChild(option);
    }
    workingRoot.value = info.definition.process?.working_root || STORAGE_ROOTS[0];
    form.append(...processFields({ command, argvAllowlist, envPassthrough, workingRoot }));
  } else {
    url = document.createElement("input");
    url.type = "url";
    url.placeholder = "https://server.example/mcp";
    url.required = true;
    url.dataset.draftKey = `edit-mcp:${info.extension_id}:url`;
    url.value = info.definition.url || "";
    form.appendChild(field("Server URL", url));
  }

  const toolAllowlist = document.createElement("input");
  toolAllowlist.placeholder = "Comma-separated, optional";
  toolAllowlist.dataset.draftKey = `edit-mcp:${info.extension_id}:tool-allowlist`;
  toolAllowlist.value = (info.definition.tool_allowlist || []).join(", ");
  const resourceAllowlist = document.createElement("input");
  resourceAllowlist.placeholder = "Comma-separated, optional";
  resourceAllowlist.dataset.draftKey = `edit-mcp:${info.extension_id}:resource-allowlist`;
  resourceAllowlist.value = (info.definition.resource_allowlist || []).join(", ");
  const promptAllowlist = document.createElement("input");
  promptAllowlist.placeholder = "Comma-separated, optional";
  promptAllowlist.dataset.draftKey = `edit-mcp:${info.extension_id}:prompt-allowlist`;
  promptAllowlist.value = (info.definition.prompt_allowlist || []).join(", ");
  form.append(field("Allowed tools", toolAllowlist), field("Allowed resources", resourceAllowlist), field("Allowed prompts", promptAllowlist));
  const credentialRef = appendCredentialRefField(form, `edit-mcp:${info.extension_id}`, info.definition.credential_ref);
  if (!isStdio) oauthFields = appendOauthFieldset(form, `edit-mcp:${info.extension_id}`, info.definition.oauth);
  const submit = button("Save connection", {
    type: "submit",
    variant: "primary",
    disabled: state.editConnectionPending,
    focusKey: `edit-mcp-submit:${info.extension_id}`,
  });
  form.append(buttonRow(submit, renderCancelEdit(state, `edit-mcp-cancel:${info.extension_id}`)));
  if (state.editConnectionError) appendText(form, state.editConnectionError, "p", "extensions-error");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const shared = {
      localId: info.local_id,
      name: name.value.trim(),
      toolAllowlist: toolAllowlist.value,
      resourceAllowlist: resourceAllowlist.value,
      promptAllowlist: promptAllowlist.value,
      credentialRef: credentialRef.value.trim(),
    };
    if (isStdio) {
      state.actions.updateMcpConnection({
        ...shared,
        command: command.value,
        argvAllowlist: argvAllowlist.value,
        envPassthrough: envPassthrough.value,
        workingRoot: workingRoot.value,
      });
    } else {
      state.actions.updateMcpConnection({
        ...shared,
        url: url.value.trim(),
        oauth: collectOauthFromFields(oauthFields),
      });
    }
  });
  return form;
}

function renderEditLocalTool(state) {
  const info = state.definition;
  const family = String(info.extension_id).split(":")[0];
  const labels = COMMAND_FAMILIES[family];
  const form = document.createElement("form");
  form.className = `extensions-edit-${family}`;
  appendText(form, `Edit ${labels.title}`, "strong");
  const name = document.createElement("input");
    name.required = true;
  name.dataset.draftKey = `edit-tool:${info.extension_id}:name`;
  name.value = info.name;
  const command = document.createElement("textarea");
  command.placeholder = "One argv token per line";
  command.required = true;
  command.dataset.draftKey = `edit-tool:${info.extension_id}:command`;
  command.value = (info.definition.command || []).join("\n");
  const argvAllowlist = document.createElement("input");
  argvAllowlist.placeholder = "Comma-separated, e.g. python3";
  argvAllowlist.required = true;
  argvAllowlist.dataset.draftKey = `edit-tool:${info.extension_id}:argv-allowlist`;
  argvAllowlist.value = (info.definition.process?.argv_allowlist || []).join(", ");
  const envPassthrough = document.createElement("input");
  envPassthrough.placeholder = "Comma-separated, optional";
  envPassthrough.dataset.draftKey = `edit-tool:${info.extension_id}:env-passthrough`;
  envPassthrough.value = (info.definition.process?.env_passthrough || []).join(", ");
  const workingRoot = document.createElement("select");
  workingRoot.dataset.draftKey = `edit-tool:${info.extension_id}:working-root`;
  for (const root of STORAGE_ROOTS) {
    const option = document.createElement("option");
    option.value = root;
    option.textContent = root;
    workingRoot.appendChild(option);
  }
  workingRoot.value = info.definition.process?.working_root || STORAGE_ROOTS[0];
  const submit = button(`Save ${labels.noun}`, {
    type: "submit",
    variant: "primary",
    disabled: state.editToolPending,
    focusKey: `edit-tool-submit:${info.extension_id}`,
  });
  form.append(
    field("Name", name),
    ...processFields({ command, argvAllowlist, envPassthrough, workingRoot }),
    buttonRow(submit, renderCancelEdit(state, `edit-tool-cancel:${info.extension_id}`)),
  );
  if (state.editToolError) appendText(form, state.editToolError, "p", "extensions-error");
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    state.actions.updateLocalTool({
      family,
      localId: info.local_id,
      name: name.value.trim(),
      command: command.value,
      argvAllowlist: argvAllowlist.value,
      envPassthrough: envPassthrough.value,
      workingRoot: workingRoot.value,
    });
  });
  return form;
}

function renderCatalog(state) {
  const section = document.createElement("section");
  section.className = "extensions-section";
  appendText(section, "Installed extensions", "h3");
  const add = document.createElement("div");
  add.className = "extensions-buttons";
  for (const [kind, text] of ADD_FORMS) {
    const btn = button(text, {
      focusKey: `add:${kind}`,
      onClick: () => state.actions.startAdd(kind),
    });
    btn.setAttribute("aria-pressed", String(state.adding === kind));
    add.appendChild(btn);
  }
  section.appendChild(add);
  if (state.catalogLoading) {
    appendText(section, "Loading extensions…", "p", "extensions-help");
    return section;
  }
  if (state.catalogError) {
    appendText(section, state.catalogError, "p", "extensions-error");
    return section;
  }
  const extensions = state.catalog?.extensions || [];
  if (!extensions.length) {
    appendText(section, "No extensions are registered.", "p", "extensions-help");
    return section;
  }

  const families = Object.entries(state.catalog?.families || {});
  if (families.length) {
    const filter = document.createElement("select");
    filter.dataset.focusKey = "filter:family";
    for (const [family, count] of [["", extensions.length], ...families]) {
      const option = document.createElement("option");
      option.value = family;
      option.textContent = family ? `${humanize(family, FAMILY_TEXT)} (${count})` : `All (${count})`;
      option.selected = state.familyFilter === family;
      filter.appendChild(option);
    }
    filter.addEventListener("change", () => state.actions.filterFamily(filter.value));
    section.appendChild(field("Show", filter));
  }

  const list = document.createElement("ul");
  list.className = "extensions-list";
  for (const extension of extensions) {
    if (state.familyFilter && extension.family !== state.familyFilter) continue;
    const item = document.createElement("li");
    const row = document.createElement("button");
    row.type = "button";
    row.className = "extensions-row";
    row.dataset.focusKey = `row:${extension.extension_id}`;
    row.dataset.state = extensionActivityState(extension);
    row.setAttribute("aria-pressed", String(state.selectedExtensionId === extension.extension_id));
    appendText(row, extension.display_name, "strong");
    appendText(row, formatExtensionOrigin(extension), "span", "extensions-row-meta");
    row.addEventListener("click", () => state.actions.selectExtension(extension.extension_id));
    item.appendChild(row);
    if (extension.unavailable_explanation) {
      appendText(item, extension.unavailable_explanation, "p", "extensions-help");
    }
    for (const collision of extension.collisions || []) {
      appendText(item, collision, "p", "extensions-error");
    }
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

function renderDetail(state) {
  const section = document.createElement("section");
  section.className = "extensions-section";
  appendText(section, "Extension detail", "h3");
  if (state.detailLoading) {
    appendText(section, "Loading extension…", "p", "extensions-help");
    return section;
  }
  // Without a detail the error is why it could not load; with one, an action on it failed and
  // the detail stays in view so the operator can see and retry.
  if (state.detailError) appendText(section, state.detailError, "p", "extensions-error");
  if (!state.detail) {
    if (!state.detailError) appendText(section, "Select an extension to inspect it.", "p", "extensions-help");
    return section;
  }
  const detail = state.detail;
  appendText(section, detail.display_name || detail.extension_id, "strong");
  const status = appendText(section, statusText(detail.state), "p", "extensions-status");
  status.dataset.state = extensionActivityState(detail);

  const facts = document.createElement("dl");
  facts.className = "extensions-facts";
  labeledValue(facts, "Family", humanize(detail.family, FAMILY_TEXT));
  labeledValue(facts, "Version", detail.version);
  labeledValue(facts, "Trust", humanize(detail.trust));
  labeledValue(facts, "Readiness", statusText(detail.readiness));
  labeledValue(facts, "Availability", humanize(detail.availability));
  section.appendChild(facts);

  // Identifier, provenance, source (a raw file/module path), and revision (an
  // optimistic-concurrency counter) are backend/audit internals, not operator-meaningful state -
  // they belong in an explicit detail disclosure, not the primary facts read at a glance.
  const advanced = document.createElement("details");
  const advancedSummary = document.createElement("summary");
  advancedSummary.textContent = "Details";
  advanced.appendChild(advancedSummary);
  const advancedFacts = document.createElement("dl");
  advancedFacts.className = "extensions-facts";
  labeledValue(advancedFacts, "Identifier", detail.extension_id);
  labeledValue(advancedFacts, "Provenance", detail.provenance);
  labeledValue(advancedFacts, "Source", detail.source);
  labeledValue(advancedFacts, "Revision", detail.revision);
  advanced.appendChild(advancedFacts);
  section.appendChild(advanced);

  const requested = requestedCapabilities(detail);
  if (requested.length) {
    const block = document.createElement("div");
    block.className = "extensions-requested";
    appendText(block, "Requested capabilities", "h4");
    appendText(
      block,
      "These are requests recorded for you, not permissions this extension holds.",
      "p",
      "extensions-help",
    );
    const list = document.createElement("ul");
    list.className = "extensions-list";
    for (const capability of requested) {
      const item = document.createElement("li");
      appendText(item, capability);
      list.appendChild(item);
    }
    block.appendChild(list);
    section.appendChild(block);
  }

  const buttons = document.createElement("div");
  buttons.className = "extensions-buttons";
  const enabled = extensionStateEnabled(detail, state.mutationPending);
  for (const next of ["enabled", "disabled", "retired"]) {
    if (next === detail.state) continue;
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.focusKey = `state:${detail.extension_id}:${next}`;
    button.textContent = next === "retired" ? "Retire" : next === "enabled" ? "Enable" : "Disable";
    if (next === "retired") button.className = "btn-danger";
    button.disabled = !enabled;
    button.addEventListener("click", () => state.actions.setState(detail.extension_id, next));
    buttons.appendChild(button);
  }
  if (detail.body_available) {
    const body = document.createElement("button");
    body.type = "button";
    body.dataset.focusKey = `show-body:${detail.extension_id}`;
    body.textContent = "Show body";
    body.disabled = state.mutationPending;
    body.addEventListener("click", () => state.actions.loadBody(detail.extension_id));
    buttons.appendChild(body);
  }
  section.appendChild(buttons);

  const runtime = document.createElement("div");
  runtime.className = "extensions-requested";
  if (state.runtime?.operations?.length) {
    const groups = new Map();
    for (const operation of state.runtime.operations) {
      const kind = operationKind(operation);
      if (!groups.has(kind)) groups.set(kind, []);
      groups.get(kind).push(operation);
    }
    const groupHeadings = { tool: "Tools", resource: "Resources", prompt: "Prompts", other: "Operations" };
    for (const kind of ["discover", "tool", "resource", "prompt", "other"]) {
      const operations = groups.get(kind);
      if (!operations?.length) continue;
      if (groupHeadings[kind]) appendText(runtime, groupHeadings[kind], "h4");
      for (const operation of operations) {
        const form = document.createElement("form");
        appendText(form, kind === "discover" ? operationDisplayName(operation) : operationShortLabel(operation), "strong");
        const fields = operation.input_schema?.properties || {};
        const complex = Object.values(fields).some((schema) => ["object", "array"].includes(schema.type));
        const inputs = [];
        if (complex) {
          const json = document.createElement("textarea");
          json.dataset.draftKey = `${detail.extension_id}:${operation.capability_id}:$json`;
          json.required = true;
          form.appendChild(field("Arguments (JSON)", json));
          inputs.push(["$json", json, { type: "json" }]);
        }
        for (const [name, schema] of complex ? [] : Object.entries(fields)) {
          const input = document.createElement("input");
          input.dataset.draftKey = `${detail.extension_id}:${operation.capability_id}:${name}`;
          input.name = name;
          input.required = (operation.input_schema?.required || []).includes(name);
          if (Array.isArray(schema.enum)) { const select = document.createElement("select"); select.dataset.draftKey = input.dataset.draftKey; for (const value of schema.enum) { const option = document.createElement("option"); option.value = value; option.textContent = value; select.appendChild(option); } inputs.push([name, select, schema]); form.appendChild(field(name, select)); continue; }
          input.type = schema.type === "boolean" ? "checkbox" : schema.type === "number" || schema.type === "integer" ? "number" : "text";
          form.appendChild(field(name, input));
          inputs.push([name, input, schema]);
        }
        const submit = button(operationSubmitLabel(operation), {
          type: "submit",
          disabled: !operation.available,
          focusKey: `operation-submit:${detail.extension_id}:${operation.capability_id}`,
        });
        // One per discovered operation; a column of accent buttons would drown the primary actions.
        submit.className = "btn-secondary";
        form.appendChild(submit);
        form.addEventListener("submit", (event) => {
          event.preventDefault();
          let argumentsValue;
          try {
            argumentsValue = inputs[0]?.[0] === "$json" ? JSON.parse(inputs[0][1].value) : Object.fromEntries(inputs.map(([name, input, schema]) => [name, schema.type === "boolean" ? input.checked : schema.type === "number" || schema.type === "integer" ? Number(input.value) : input.value]));
          } catch {
            state.actions.notice("Arguments must be valid JSON.");
            return;
          }
          state.actions.invoke(detail.extension_id, operation.capability_id, argumentsValue);
        });
        runtime.appendChild(form);
      }
    }
  }
  if (detail.family === "mcp") {
    // A server that demands authorization before it will answer discovery has no
    // operations yet, so the credential form must not depend on having any.
    const credential = document.createElement("form");
    appendText(credential, "Credential", "strong");
    const name = document.createElement("input");
    name.required = true;
    name.dataset.draftKey = `${detail.extension_id}:credential:name`;
    const secret = document.createElement("input");
    secret.type = "password";
    secret.required = true;
    const save = button("Store credential", {
      type: "submit",
      variant: "primary",
      focusKey: `credential-submit:${detail.extension_id}`,
    });
    credential.append(field("Name", name), field("Secret", secret), buttonRow(save));
    credential.addEventListener("submit", (event) => {
      event.preventDefault();
      state.actions.credential(detail.extension_id, name.value, secret.value);
      secret.value = "";
    });
    runtime.appendChild(credential);
    const manage = buttonRow();
    runtime.appendChild(manage);
    // Ends the held session without touching the definition or stored credentials -
    // distinct from "Remove connection" (deletes the definition) and "Forget
    // authorization" (clears a stored OAuth token) below. Safe to click regardless of
    // current connection state; disconnecting an already-closed connection is a no-op.
    const disconnect = button("Disconnect", {
      focusKey: `disconnect:${detail.extension_id}`,
      disabled: state.mutationPending,
      onClick: () => state.actions.disconnect(detail.extension_id),
    });
    manage.appendChild(disconnect);
    if (detail.definition_available) {
      if (state.definition?.extension_id === detail.extension_id) {
        runtime.appendChild(renderEditMcpConnection(state));
      } else {
        const edit = button("Edit connection", {
          focusKey: `edit-connection:${detail.extension_id}`,
          disabled: state.mutationPending,
          onClick: () => state.actions.loadDefinition(detail.extension_id),
        });
        manage.appendChild(edit);
      }
    }
    if (isOperatorOwnedProvenance(detail)) {
      const remove = button("Remove connection", {
        variant: "danger",
        focusKey: `remove-connection:${detail.extension_id}`,
        disabled: state.mutationPending,
        onClick: () => state.actions.removeMcpConnection(detail.local_id),
      });
      manage.appendChild(remove);
    }
    // snapshot.health is a cached fact from the last discover call, not a live read - a
    // probe reproduced it still reading "ready" after Disconnect closed the session.
    // `connected` is the backend's own live signal (SessionManager.is_open) and
    // overrides a stale "ready" the moment it reports false, rather than treating the
    // cached health as still current.
    const health = state.runtime?.snapshot?.health;
    const connected = state.runtime?.connected;
    const healthLabel = connected === false ? "not connected" : health;
    if (healthLabel) {
      appendText(runtime, `Connection health: ${healthLabel}`, "p");
    }
    if (state.oauthStatus?.configured) {
      const oauth = document.createElement("div");
      appendText(oauth, "OAuth", "strong");
      appendText(
        oauth,
        state.oauthStatus.authorized ? "Authorized." : "Not authorized.",
        "p",
      );
      if (state.oauth?.extensionId === detail.extension_id) {
        // The backend holds the verifier and state; the operator only carries the code back.
        const link = document.createElement("a");
        link.href = state.oauth.url;
        link.textContent = "Open authorization page";
        link.target = "_blank";
        link.rel = "noreferrer noopener";
        oauth.appendChild(link);
        const finish = document.createElement("form");
        const code = document.createElement("input");
        code.required = true;
        code.dataset.focusKey = `oauth:${detail.extension_id}:code`;
        code.dataset.draftKey = `oauth:${detail.extension_id}:code`;
        const submit = button("Complete authorization", {
          type: "submit",
          variant: "primary",
        });
        finish.append(field("Authorization code", code), buttonRow(submit));
        finish.addEventListener("submit", (event) => {
          event.preventDefault();
          state.actions.completeOauth(detail.extension_id, code.value);
        });
        oauth.appendChild(finish);
      } else {
        const connect = button(state.oauthStatus.authorized ? "Reconnect" : "Connect", {
          disabled: state.mutationPending,
          onClick: () => state.actions.startOauth(detail.extension_id),
        });
        oauth.appendChild(connect);
        if (state.oauthStatus.authorized) {
          // "Forget authorization" clears the client's own stored token; the MCP
          // authorization specification defines no revocation flow this needs to call, and
          // is a distinct concept from Disconnect (ending an active connection), which does
          // not yet exist as a separate action.
          const forget = button("Forget authorization", {
            disabled: state.mutationPending,
            onClick: () => state.actions.forgetOauth(detail.extension_id),
          });
          oauth.appendChild(forget);
        }
      }
      runtime.appendChild(oauth);
    }
  }
  const commandFamily = COMMAND_FAMILIES[detail.family];
  if (commandFamily && isOperatorOwnedProvenance(detail)) {
    const manage = buttonRow();
    runtime.appendChild(manage);
    if (detail.definition_available) {
      if (state.definition?.extension_id === detail.extension_id) {
        runtime.appendChild(renderEditLocalTool(state));
      } else {
        const edit = button(`Edit ${commandFamily.noun}`, {
          focusKey: `edit-${detail.family}:${detail.extension_id}`,
          disabled: state.mutationPending,
          onClick: () => state.actions.loadDefinition(detail.extension_id),
        });
        manage.appendChild(edit);
      }
    }
    const remove = button(`Remove ${commandFamily.noun}`, {
      variant: "danger",
      focusKey: `remove-${detail.family}:${detail.extension_id}`,
      disabled: state.mutationPending,
      onClick: () => state.actions.removeLocalTool(detail.local_id, detail.family),
    });
    manage.appendChild(remove);
  }
  if (detail.family === "skill" && String(detail.provenance || "").startsWith("data/extensions")) {
    // Operator-authored skills live under data/extensions and carry external trust;
    // application skills stay read-only. Provenance, not trust, is the ownership test.
    const editor = document.createElement("form");
    appendText(editor, "Edit skill", "strong");
    const body = document.createElement("textarea");
    // The draft key is only assigned once a body has actually loaded. renderPanel's
    // capture-then-restore step would otherwise stomp a freshly loaded body back to the
    // pre-load empty value: the outgoing tree (captured before this render) has no draft-key
    // entry for this field while state.body is still empty, so the very re-render that first
    // populates state.body has nothing to restore and the seeded value survives; only later
    // re-renders, once the key exists on both sides, preserve an operator's in-progress edit.
    if (state.body) body.dataset.draftKey = `${detail.extension_id}:skill-body`;
    body.value = state.body || "";
    body.required = true;
    const save = button("Save skill", {
      type: "submit",
      variant: "primary",
      disabled: state.mutationPending,
    });
    const remove = button("Remove skill", {
      variant: "danger",
      disabled: state.mutationPending,
      onClick: () => state.actions.removeSkill(detail.local_id),
    });
    editor.append(field("Skill file", body), buttonRow(save, remove));
    editor.addEventListener("submit", (event) => {
      event.preventDefault();
      state.actions.saveSkill(detail.local_id, body.value);
    });
    runtime.appendChild(editor);
  }
  if (runtime.childNodes.length) {
    section.appendChild(runtime);
  }
  const runs = state.runs.filter((run) => run.extension_id === detail.extension_id);
  if (runs.length) {
    const block = document.createElement("div"); block.className = "extensions-requested";
    appendText(block, "Runs", "h4");
    for (const run of runs) {
      appendText(block, `${extensionRunTitle(run)} · ${formatRunStarted(run.started_at)}`, "strong");
      // A run's id and proposal id are backend correlation identifiers, not something an
      // operator reads to understand what happened - they stay reachable for audit, behind
      // the same kind of disclosure the extension-level Source/Revision fields already use.
      const runDetails = document.createElement("details");
      const runSummary = document.createElement("summary");
      runSummary.textContent = "Run details";
      runDetails.appendChild(runSummary);
      const runFacts = document.createElement("dl");
      runFacts.className = "extensions-facts";
      labeledValue(runFacts, "Run ID", run.run_id);
      labeledValue(runFacts, "Proposal", run.proposal_id);
      runDetails.appendChild(runFacts);
      if (run.arguments && Object.keys(run.arguments).length) {
        const input = document.createElement("dl");
        input.className = "extensions-facts";
        appendText(block, "Requested input", "h5");
        for (const [key, value] of Object.entries(run.arguments)) {
          labeledValue(input, key, typeof value === "string" ? value : JSON.stringify(value));
        }
        block.appendChild(input);
      }
      if (run.events?.length) appendText(runDetails, JSON.stringify(run.events, null, 2), "pre");
      if (run.result) appendText(runDetails, JSON.stringify(run.result, null, 2), "pre");
      block.appendChild(runDetails);
      if (run.error) appendText(block, run.error, "p", "extensions-row-meta");
      appendRunControls(block, run, state.actions);
      if (run.events?.length) {
        const event = run.events.at(-1);
        appendText(block, `Latest event: ${String(event.type || event.kind || "update").replaceAll("_", " ")}`, "p", "extensions-row-meta");
      }
      if (run.result) {
        const messages = formatPromptMessages(run.result);
        const resourceContents = messages ? null : formatResourceContents(run.result);
        if (messages) {
          for (const message of messages) appendText(block, `${message.role}: ${message.text}`, "p", "extensions-row-meta");
        } else if (resourceContents) {
          for (const item of resourceContents) {
            if (item.kind === "text") {
              appendText(block, item.text, "pre", "extensions-row-meta");
            } else {
              const image = document.createElement("img");
              image.src = item.dataUrl;
              image.alt = item.uri || "resource content";
              image.className = "extensions-row-meta";
              block.appendChild(image);
            }
          }
        } else {
          const toolText = formatToolResult(run.result);
          if (toolText !== null) appendText(block, toolText, "pre", "extensions-row-meta");
          else if (run.operation === "discover") {
            appendText(block, `Discovered ${run.result.tools?.length || 0} tools, ${run.result.resources?.length || 0} resources, and ${run.result.prompts?.length || 0} prompts.`, "p", "extensions-row-meta");
          } else appendText(block, "Result available in Run details.", "p", "extensions-row-meta");
        }
        const artifacts = run.result.artifacts || run.result.content?.artifacts;
        if (Array.isArray(artifacts) && artifacts.length) {
          appendText(block, "Artifacts", "h5");
          for (const artifact of artifacts) appendText(block, typeof artifact === "string" ? artifact : artifact.path || artifact.name || "Artifact available in Run details", "p");
        }
      }
    }
    section.appendChild(block);
  }

  if (state.body) {
    const body = document.createElement("details");
    body.open = true;
    appendText(body, "Body", "summary");
    appendText(body, state.body, "pre");
    section.appendChild(body);
  }
  return section;
}

function renderErrors(state) {
  const section = document.createElement("section");
  section.className = "extensions-section";
  appendText(section, "Load errors", "h3");
  if (state.errorsLoading) {
    appendText(section, "Loading errors…", "p", "extensions-help");
    return section;
  }
  if (state.errorsError) {
    appendText(section, state.errorsError, "p", "extensions-error");
    return section;
  }
  if (!state.errors.length) {
    appendText(section, "Every extension loaded cleanly.", "p", "extensions-help");
    return section;
  }
  const list = document.createElement("ul");
  list.className = "extensions-list";
  for (const error of state.errors) {
    const item = document.createElement("li");
    appendText(item, `${error.family} · ${error.source}`, "strong");
    appendText(item, error.reason, "span", "extensions-row-meta");
    list.appendChild(item);
  }
  section.appendChild(list);
  return section;
}

function renderPanel(state) {
  const layout = document.createElement("div");
  layout.className = "extensions-panel-layout";
  const listColumn = document.createElement("div");
  listColumn.className = "extensions-panel-list";
  listColumn.dataset.scrollKey = "list";
  listColumn.append(renderCatalog(state), renderErrors(state));
  const detailColumn = document.createElement("div");
  detailColumn.className = "extensions-panel-detail";
  detailColumn.dataset.scrollKey = "detail";
  detailColumn.appendChild(state.adding ? renderAddForm(state) : renderDetail(state));
  layout.append(listColumn, detailColumn);
  return [
    renderPanelHeader("Extensions"),
    messageRegion({ notice: state.notice, error: state.conflict }),
    layout,
  ];
}

export function createExtensionsPanel(container, handlers, options = {}) {
  let controller;
  const confirm = options.confirmCancel || confirmDestructive;
  // Removing, retiring, or forgetting cannot be undone, so each asks first.
  const confirmed = (message, run, confirmOptions) => async (...args) => ((await confirm(message, confirmOptions)) ? run(...args) : null);
  const actions = {
    selectExtension: (extensionId) => controller.selectExtension(extensionId),
    loadBody: (extensionId) => controller.loadBody(extensionId),
    loadDefinition: (extensionId) => controller.loadDefinition(extensionId),
    cancelDefinitionEdit: () => controller.cancelDefinitionEdit(),
    setAddConnectionTransport: (transport) => controller.setAddConnectionTransport(transport),
    setState: (extensionId, next) => (next === "retired"
      ? confirmed("Retire this extension? It stops being offered anywhere.", () => controller.setState(extensionId, next))()
      : controller.setState(extensionId, next)),
    filterFamily: (family) => controller.filterFamily(family),
    startAdd: (kind) => controller.startAdd(kind),
    cancelAdd: () => controller.cancelAdd(),
    invoke: (extensionId, capabilityId, argumentsValue) => controller.invoke(extensionId, capabilityId, argumentsValue),
    answer: (runId, requestId, answerValue) => controller.answer(runId, requestId, answerValue),
    credential: (extensionId, name, secret) => controller.credential(extensionId, name, secret),
    importSkill: (localId, body) => controller.importSkill(localId, body),
    saveSkill: (localId, body) => controller.saveSkill(localId, body),
    removeSkill: confirmed("Remove this skill?", (localId) => controller.removeSkill(localId)),
    addMcpConnection: (payload) => controller.addMcpConnection(payload),
    updateMcpConnection: (payload) => controller.updateMcpConnection(payload),
    removeMcpConnection: confirmed("Remove this connection?", (localId) => controller.removeMcpConnection(localId)),
    addLocalTool: (payload) => controller.addLocalTool(payload),
    updateLocalTool: (payload) => controller.updateLocalTool(payload),
    removeLocalTool: (localId, family) => confirmed(
      `Remove this ${COMMAND_FAMILIES[family || "tool"].noun}?`,
      () => controller.removeLocalTool(localId, family),
    )(),
    startOauth: (extensionId) => controller.startOauth(extensionId),
    completeOauth: (extensionId, code) => controller.completeOauth(extensionId, code),
    forgetOauth: confirmed("Forget the stored authorization?", (extensionId) => controller.forgetOauth(extensionId)),
    disconnect: confirmed(
      "Disconnect this connection? In-flight operations will terminate.",
      (extensionId) => controller.disconnect(extensionId),
      { confirmLabel: "Disconnect" },
    ),
    decide: (proposalId, outcome) => controller.decide(proposalId, outcome),
    cancel: (proposalId) => controller.cancel(proposalId, confirm),
    notice: (message) => controller.notice(message),
  };
  const lifecycle = createPanelLifecycle(container, {
    load: () => controller.load(),
    render: (state) => renderPanel({ ...state, actions }),
    cancelPendingReads: () => controller.cancelPendingReads(),
    onClose: options.onClose,
    // Runs stream progress and may stop to ask for input; follow them only while one is live.
    // An invocation that has not returned counts: its run is not listed yet, and it may be
    // waiting on the very input request only this poll can surface.
    poll: {
      active: () => {
        const snapshot = controller.snapshot();
        return snapshot.invocationsInFlight > 0 || snapshot.runs.some((run) => ACTIVE_RUN_STATUSES.includes(run.status));
      },
      run: () => controller.refreshRuns(),
    },
  });
  controller = createExtensionsPanelController(handlers, lifecycle.draw);
  return { open: lifecycle.open, close: lifecycle.close, isOpen: lifecycle.isOpen, controller };
}
