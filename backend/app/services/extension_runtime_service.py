from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

import yaml
from backend.app.actions.boundaries import (
    ActionCancelledError,
    ActionOperation,
    ProcessBoundary,
    bound_result,
)
from backend.app.actions.contracts import (
    CapabilityDescriptor,
    default_authorization,
    validate_schema,
)
from backend.app.actions.process import run_process
from backend.app.actions.sessions import SessionCallOutcomeUnknownError, SessionManager
from backend.app.artifacts.storage import write_text_atomic
from backend.app.core.paths import CONFIG_DIR, DATA_DIR
from backend.app.extensions.contracts import SAFE_LOCAL_ID
from backend.app.extensions.discovery import (
    DEFINITION_FAMILIES,
    DefinitionFamily,
    DefinitionManifest,
    definition_fingerprint,
    definitions_directory,
    discover_definition_manifests,
    parse_definition_manifest,
)
from backend.app.extensions.hooks import HookRunner
from backend.app.extensions.runs import ExtensionRuns, McpSnapshots
from backend.app.extensions.skills import resolve_skill_script
from backend.app.extensions.store import ExtensionOverlayStore
from backend.app.services.capability_service import CapabilityService, mask_arguments

ENDPOINT_ONLY_CAPABILITIES = {
    "extension-input-answer": "backend.app.api.routes.extensions.answer_extension_input",
    "extension-credential-write": "backend.app.api.routes.extensions.write_extension_credential",
}


def operation_id(extension_id: str, name: str) -> str:
    digest = hashlib.sha256(f"{extension_id}:{name}".encode()).hexdigest()[:24]
    return f"extension-{digest}"


def _authorization_for(family: str, effect_class: str, operation: str = "") -> str:
    # Executable installation and server-declared tool effects cannot grant model authority.
    if family == "plugin" or (family == "mcp" and operation.startswith("tool:")):
        return "requires_approval"
    return default_authorization(effect_class)


def _mcp_tool_effect(tool: dict[str, Any], transport: str) -> str:
    # Server hints describe effects but cannot grant authority to model proposals.
    annotations = tool.get("annotations")
    if isinstance(annotations, dict):
        if annotations.get("destructiveHint") is True:
            return "destructive_action"
        if annotations.get("readOnlyHint") is True:
            return "external_read"
    return "privileged_execution" if transport == "stdio" else "external_write"


class ExtensionRuntimeService:
    def __init__(self, actions: CapabilityService, *, config_dir: Path | None = None,
                 data_dir: Path | None = None, db_path: Path | None = None) -> None:
        self.actions = actions
        self.config_dir = config_dir or CONFIG_DIR
        self.data_dir = data_dir or DATA_DIR
        self.overlay = ExtensionOverlayStore(db_path)
        self.runs = ExtensionRuns(db_path)
        self.snapshots = McpSnapshots(store=self.runs.store)
        self.hooks = HookRunner(actions, self.definitions)
        # Discovery survives restart, so an operator does not have to rediscover every
        # connection before its tools are proposable again.
        self._snapshots: dict[str, dict[str, Any]] = self.snapshots.all()
        self._operations: dict[str, list[dict[str, Any]]] = {}
        self._errors: dict[str, str] = {}
        self._load_errors: dict[str, str] = {}
        self._oauth_flows: dict[str, tuple[Any, str]] = {}
        # ADR 0005's shared session-lifecycle mechanism: keeps an MCP stdio connection's
        # or an ACP agent process's session open across operations instead of one
        # process per call. Shared across both families - connection ids are namespaced
        # ("mcp:...", "acp:...") so they cannot collide.
        self._sessions = SessionManager()
        # Calls against one reused MCP connection are serialized by _sessions itself, so
        # exactly one entry is ever "current" per identifier at a time. _mcp's elicit
        # callback is baked into the connection's McpHostCallbacks only on the first call
        # that opens it, so it reads run_id/operation from here instead of closing over
        # them, letting a later call's elicitation route to that call's own run.
        self._mcp_call_context: dict[str, tuple[str, ActionOperation]] = {}
        # The last session id `run_acp` opened for a given ACP connection, so a later
        # call whose connection was evicted and reopened (a crashed process, an explicit
        # Disconnect) can attempt `session/resume` against it instead of always starting
        # a fresh session - see `_open_session_id` in `backend/app/extensions/acp.py`.
        self._acp_session_ids: dict[str, str] = {}
        self._lock = threading.RLock()
        self.session_executor: Callable[..., dict[str, Any]] | None = None
        actions.bind_extensions(self.bindings)

    def definitions(self) -> list[DefinitionManifest]:
        overlays = self.overlay.all_overlays()
        result = []
        for family in sorted(DEFINITION_FAMILIES):
            for manifest in discover_definition_manifests(
                family, config_root=self.config_dir, data_root=self.data_dir,
            ).manifests:
                state = overlays.get(f"{family}:{manifest.local_id}", (None, None))[0]
                enabled = state == "enabled" if state is not None else manifest.declared_enabled
                result.append(replace(manifest, declared_enabled=enabled))
        from backend.app.extensions.discovery import parse_definition_manifest
        from backend.app.extensions.plugins import PluginInstaller
        seen = {(item.family, item.local_id) for item in result}
        parents = {item.local_id: item for item in result if item.family == "plugin"}
        try:
            children = PluginInstaller(self.config_dir, self.data_dir).installed_definitions()
            self._load_errors.pop("plugin:installed", None)
        except (OSError, ValueError):
            children = ()
            self._load_errors["plugin:installed"] = "Installed plugin contents could not be verified."
        for child in children:
            if (child.family, child.local_id) in seen or child.plugin_id not in parents:
                continue
            manifest = parse_definition_manifest(child.family, child.path.read_text(encoding="utf-8"),
                                                 str(child.path), "data/extensions", "external")
            if manifest.local_id != child.local_id:
                continue
            enabled = parents[child.plugin_id].declared_enabled and manifest.declared_enabled
            state = overlays.get(f"{child.family}:{child.local_id}", (None, None))[0]
            result.append(replace(manifest, declared_enabled=enabled and state not in {"disabled", "retired"}))
            seen.add((child.family, child.local_id))
        return result

    def bindings(self) -> list[tuple[CapabilityDescriptor, Callable]]:
        bindings = []
        operations: dict[str, list[dict[str, Any]]] = {}
        errors = {}
        # These two carry a live run's pending request or a secret value, so they are driven by
        # their own route and never by a generic proposal; they register with no executor.
        for name, owner in ENDPOINT_ONLY_CAPABILITIES.items():
            bindings.append((CapabilityDescriptor(
                capability_id=name, source="backend.extension_runtime", provenance="application",
                input_schema={"type": "object"}, effect_class="local_write", readiness="ready", availability="available",
                authorization_rule=default_authorization("local_write"), execution_owner=owner,
                timeout_policy={"timeout_ms": 30000}, cancellation_policy={"cancellable": False},
                result_schema={"type": "object"}, artifact_evidence={"records": True}, unavailable_explanation="",
            ), None))
        for manifest in self.definitions():
            identifier = f"{manifest.family}:{manifest.local_id}"
            try:
                for name, schema, effect, handler in self._operations_for(manifest):
                    validate_schema(schema)
                    process = manifest.definition.get("process")
                    if effect == "privileged_execution":
                        ProcessBoundary.from_mapping(process or {})
                    boundary = {"storage_roots": [process["working_root"]] if process else ["data"],
                                "timeout_ms": 60000, "cancellable": True, "max_result_bytes": 64000}
                    if process:
                        boundary["process"] = process
                    fingerprint = json.dumps(manifest.definition, sort_keys=True)
                    if manifest.family == "tool" and manifest.definition.get("skill_id"):
                        script = resolve_skill_script(manifest.definition["skill_id"], manifest.definition["script"], self.data_dir, config_dir=self.config_dir)
                        fingerprint += hashlib.sha256(script.read_bytes()).hexdigest()
                    descriptor = CapabilityDescriptor(
                        capability_id=operation_id(identifier, name), source=manifest.source,
                        provenance=manifest.provenance, input_schema=schema,
                        effect_class=effect, readiness="ready", availability="available" if manifest.declared_enabled else "disabled",
                        authorization_rule=_authorization_for(manifest.family, effect, name),
                        execution_owner="backend.extension_runtime",
                        timeout_policy={"timeout_ms": 60000}, cancellation_policy={"cancellable": True},
                        result_schema={"type": "object"}, artifact_evidence={"records": True},
                        unavailable_explanation="" if manifest.declared_enabled else "Extension is disabled.",
                        boundaries=boundary,
                        metadata_claims={"definition": {"sha256": hashlib.sha256(fingerprint.encode()).hexdigest(), "trusted": False}},
                    )
                    bindings.append((descriptor, self._handler(manifest, name, handler)))
                    operations.setdefault(identifier, []).append({"name": name, "capability_id": descriptor.capability_id,
                                                                "input_schema": schema, "effect_class": effect,
                                                                "authorization_rule": descriptor.authorization_rule,
                                                                "available": manifest.declared_enabled})
                    if manifest.family == "tool" and manifest.definition.get("skill_id"):
                        operations.setdefault(f"skill:{manifest.definition['skill_id']}", []).append(operations[identifier][-1])
            except Exception as exc:
                errors[identifier] = type(exc).__name__ + ": invalid or unavailable extension definition"
        with self._lock:
            self._operations = operations
            self._errors = errors
        return bindings

    def _operations_for(self, manifest: DefinitionManifest) -> list[tuple]:
        definition = manifest.definition
        identifier = f"{manifest.family}:{manifest.local_id}"
        empty = {"type": "object", "additionalProperties": False}
        if manifest.family == "tool":
            command = definition.get("command")
            if not isinstance(command, list) or not command or any(not isinstance(part, str) for part in command):
                raise ValueError("tool requires fixed command arguments")
            ProcessBoundary.from_mapping(definition.get("process", {})).validate_argv(command)
            if definition.get("skill_id"):
                resolve_skill_script(definition["skill_id"], definition["script"], self.data_dir, config_dir=self.config_dir)
            if not ((Path(command[0]).is_absolute() and Path(command[0]).is_file()) or shutil.which(command[0])):
                raise ValueError("configured executable is unavailable")
            return [("run", empty, "privileged_execution", lambda args, op, run: self._tool(manifest, op))]
        if manifest.family == "acp":
            from backend.app.extensions.acp import AcpDefinition
            AcpDefinition.from_mapping(manifest.local_id, definition)
            schema = {"type": "object", "properties": {"prompt": {"type": "string", "minLength": 1, "maxLength": 6000}},
                      "required": ["prompt"], "additionalProperties": False}
            return [("prompt", schema, "privileged_execution", lambda args, op, run: self._acp(manifest, args, op, run))]
        if manifest.family == "plugin":
            from backend.app.extensions.plugins import PluginInstaller
            return [("install", empty, "local_write", lambda args, op, run: PluginInstaller(
                config_dir=self.config_dir, data_dir=self.data_dir,
            ).install(manifest, op))]
        if manifest.family != "mcp":
            return []
        from backend.app.extensions.mcp import McpConnectionDefinition
        connection = McpConnectionDefinition.from_mapping(manifest.local_id, definition)
        read_effect = "external_read"
        operations = [("discover", empty, read_effect, lambda args, op, run: self._mcp(manifest, "discover", args, op, run))]
        snapshot = self._snapshots.get(identifier, {})
        for tool in snapshot.get("tools", []):
            name = "tool:" + tool["name"]
            operations.append((name, tool["inputSchema"], _mcp_tool_effect(tool, connection.transport),
                               lambda args, op, run, name=name: self._mcp(manifest, name, args, op, run)))
        for resource in snapshot.get("resources", []):
            name = "resource:" + resource["uri"]
            operations.append((name, empty, read_effect, lambda args, op, run, name=name: self._mcp(manifest, name, args, op, run)))
        for prompt in snapshot.get("prompts", []):
            name = "prompt:" + prompt["name"]
            fields = prompt.get("arguments", [])
            schema = {"type": "object", "properties": {item["name"]: {"type": "string"} for item in fields},
                      "required": [item["name"] for item in fields if item.get("required")], "additionalProperties": False}
            operations.append((name, schema, read_effect, lambda args, op, run, name=name: self._mcp(manifest, name, args, op, run)))
        return operations

    def _handler(self, manifest: DefinitionManifest, name: str, handler: Callable) -> Callable:
        def execute(arguments: dict[str, Any], operation: ActionOperation) -> dict[str, Any]:
            def work() -> dict[str, Any]:
                identifier = f"{manifest.family}:{manifest.local_id}"
                current = next((item for item in self.definitions() if f"{item.family}:{item.local_id}" == identifier), None)
                if current is None or not current.declared_enabled or current.definition != manifest.definition:
                    raise ValueError("extension definition changed or was disabled")
                run_id = self.runs.create(identifier, operation)
                self.runs.update(
                    run_id, operation=name, extension_name=current.display_name,
                    arguments=mask_arguments(operation_id(identifier, name), arguments),
                )
                try:
                    result = handler(arguments, operation, run_id)
                    operation.check()
                    result = bound_result(result, operation.boundary.max_result_bytes, {})
                    self.runs.update(run_id, status="success", result=result)
                    return {"run_id": run_id, "output": result}
                except ActionCancelledError:
                    self.runs.update(run_id, status="cancelled", request=None)
                    raise
                except SessionCallOutcomeUnknownError:
                    # A timeout or cancellation left the shared session mechanism unable
                    # to tell whether the far side already executed this call -
                    # SessionCallOutcomeUnknownError exists specifically so that ambiguity is
                    # not reported as an ordinary failure, which would read as "this did
                    # not happen" and could encourage an operator to repeat a call that
                    # may already have run. Recorded and re-raised as itself, distinct
                    # from the generic RuntimeError below, so a probe confirmed both this
                    # run's own status and the capability execution status downstream
                    # (CapabilityService._run) preserve the distinction instead of both
                    # collapsing into "failure".
                    self.runs.update(run_id, status="outcome_unknown", request=None,
                                     error="The outcome is unknown. Do not repeat this call without checking its effects.")
                    raise
                except Exception as exc:
                    self.runs.update(run_id, status="failure", request=None,
                                     error="Extension execution failed; inspect its readiness and run evidence.")
                    raise RuntimeError("Extension execution failed; inspect its readiness and run evidence.") from exc
            if manifest.family == "acp" and self.session_executor:
                return self.session_executor(work, arguments, operation)
            if manifest.family == "acp":
                raise ValueError("ACP requires an active JARVIS session")
            return work()
        return execute

    def _tool(self, manifest: DefinitionManifest, operation: ActionOperation) -> dict[str, Any]:
        definition = manifest.definition
        command = list(definition["command"])
        if definition.get("skill_id"):
            skill_id = definition["skill_id"]
            overlay = self.overlay.read(f"skill:{skill_id}")
            if overlay and overlay.state in {"disabled", "retired"}:
                raise ValueError("skill is disabled")
            script = resolve_skill_script(skill_id, definition["script"], self.data_dir, config_dir=self.config_dir)
            command.insert(1, str(script))
        result, artifacts = run_process(operation, ProcessBoundary.from_mapping(definition["process"]), command)
        if result.get("exit_code", 0) != 0:
            raise ValueError("extension process exited unsuccessfully")
        return {**result, "artifacts": artifacts}

    def _acp(self, manifest: DefinitionManifest, arguments: dict[str, Any], operation: ActionOperation, run_id: str) -> dict[str, Any]:
        from backend.app.extensions.acp import AcpDefinition, run_acp
        # Matches run_acp's own connection_id shape (agent + host conversation), so a
        # remembered session id is only ever offered back to the conversation that
        # produced it - the same isolation the connection_id change itself provides.
        identifier = f"acp:{manifest.local_id}:{operation.session_id}"
        return run_acp(
            self._sessions,
            AcpDefinition.from_mapping(manifest.local_id, manifest.definition), arguments["prompt"], operation,
            on_event=lambda event: self.runs.event(run_id, event),
            request_permission=lambda request: self.runs.request(run_id, {"kind": "permission", **request}, operation),
            get_resumable_session_id=lambda: self._acp_session_ids.get(identifier),
            remember_session_id=lambda session_id: self._acp_session_ids.__setitem__(identifier, session_id),
        )

    def _mcp(self, manifest: DefinitionManifest, name: str, arguments: dict[str, Any], operation: ActionOperation, run_id: str) -> dict[str, Any]:
        from backend.app.actions.sessions import SessionHandlers, SessionResourceDiedError
        from backend.app.extensions.mcp import (
            McpConnectionDefinition,
            McpConnectionRuntime,
            McpHostCallbacks,
            open_mcp_sdk_peer,
            peer_connection_died,
        )
        definition = McpConnectionDefinition.from_mapping(manifest.local_id, manifest.definition)
        identifier = f"mcp:{manifest.local_id}"

        async def credentials(_definition: Any) -> dict[str, str]:
            return self.mcp_credentials(definition, manifest.local_id)

        async def authorize(op: ActionOperation, kind: str, request: dict[str, Any]) -> None:
            op.check()

        async def elicit(_definition: Any, request: dict[str, Any]) -> dict[str, Any]:
            # Looked up fresh rather than closed over: this callback is bound into the
            # connection's McpHostCallbacks only the first time the connection opens, but
            # the connection is reused across later calls with their own run_id/operation.
            current_run_id, current_operation = self._mcp_call_context[identifier]
            return await asyncio.to_thread(
                self.runs.request, current_run_id, {"kind": "elicitation", **request}, current_operation
            )

        async def open_runtime() -> McpConnectionRuntime:
            return McpConnectionRuntime(definition, peer_factory=open_mcp_sdk_peer,
                                         callbacks=McpHostCallbacks(credentials, authorize, elicit))

        async def close_runtime(runtime: McpConnectionRuntime) -> None:
            # For a stdio connection, this is already a genuine forceful kill, not just a
            # polite request: McpSdkPeer.aclose() exits the SDK's own Client context
            # manager, which for StdioServerParameters tears down through the SDK's
            # stdio_client - close stdin, wait, SIGTERM the process tree, wait again,
            # then SIGKILL if it is still alive (a hard Job Object kill on Windows) - all
            # inside a shield so an outer cancellation cannot cut the escalation short.
            # There is no separate, lower-level kill to reach for beyond this: `close`
            # and `terminate` are intentionally the same function for this family.
            await runtime.close()

        handlers: SessionHandlers[McpConnectionRuntime] = SessionHandlers(
            open=open_runtime, close=close_runtime, terminate=close_runtime,
        )

        async def work(runtime: McpConnectionRuntime) -> dict[str, Any]:
            self._mcp_call_context[identifier] = (run_id, operation)
            if name == "discover":
                snapshot = (await runtime.refresh(operation)).to_dict()
                self._snapshots[identifier] = snapshot
                if snapshot.get("health") != "ready":
                    # A connection that failed to answer is not one to keep dispatching
                    # calls into - evicting it here is what makes the next discover
                    # restart against a fresh connection instead of the same wedged one,
                    # matching MCP stdio's own guidance to restart after unexpected
                    # termination rather than retry against it on a schedule.
                    raise SessionResourceDiedError(snapshot.get("error") or "MCP discovery failed")
                self.snapshots.save(identifier, snapshot)
                return snapshot
            kind, value = name.split(":", 1)
            try:
                if kind == "tool":
                    result = await runtime.call_tool(operation, value, arguments)
                elif kind == "resource":
                    result = await runtime.read_resource(operation, value)
                else:
                    result = await runtime.get_prompt(operation, value, arguments)
            except Exception as exc:
                # A failed tool/resource/prompt call does not itself evict the connection
                # by default - most failures (an unlisted name, a tool-reported error, a
                # bad argument) are the server answering normally, not evidence the
                # connection is dead. Only the SDK's own signal that the connection
                # itself closed means the next call must reopen rather than retry
                # against the same now-unusable connection.
                if peer_connection_died(exc):
                    raise SessionResourceDiedError(f"MCP connection died during {kind} call: {exc}") from exc
                raise
            if hasattr(result, "model_dump"):
                result = result.model_dump(mode="json", by_alias=True)
            return {"content": result, "trusted": False}

        try:
            return self._sessions.call(identifier, handlers, work, timeout_s=operation.boundary.timeout_ms / 1000)
        except SessionResourceDiedError as exc:
            self.snapshots.delete(identifier)
            raise ValueError(str(exc)) from exc

    @staticmethod
    def _definition_family(family: str) -> DefinitionFamily:
        if family not in DEFINITION_FAMILIES:
            raise ValueError("unknown extension family")
        return cast(DefinitionFamily, family)

    def _definition_path(self, family: str, local_id: str) -> Path:
        if not SAFE_LOCAL_ID.match(local_id):
            raise ValueError(f"id must match {SAFE_LOCAL_ID.pattern}")
        _, data_dir = definitions_directory(
            self._definition_family(family), config_root=self.config_dir, data_root=self.data_dir
        )
        return data_dir / f"{local_id}.yaml"

    def write_definition(
        self,
        family: str,
        local_id: str,
        payload: dict[str, Any],
        *,
        expected_fingerprint: str | None = None,
    ) -> dict[str, Any]:
        """Create or replace an operator-owned declarative definition.

        The definition is parsed and family-validated before it is written, so a malformed
        connection is refused with its reason instead of persisted and failing later.
        An application definition of the same family and id keeps precedence and is never
        overwritten, so this cannot shadow a tracked default. `expected_fingerprint` distinguishes
        create from update: a create (no prior read) omits it and is refused if an operator
        definition with this id already exists, since silently replacing it would not be a create
        at all; an edit of a definition already read back through `ExtensionService.definition`
        supplies it, and the write is refused if the stored definition no longer matches - has
        changed, or has disappeared - so a stale editor cannot silently overwrite either a
        concurrent change or nothing at all.
        """
        definition_family = self._definition_family(family)
        path = self._definition_path(family, local_id)
        document = {**payload, "id": local_id}
        text = yaml.safe_dump(document, sort_keys=False, allow_unicode=True)
        manifest = parse_definition_manifest(
            definition_family, text, str(path), "data/extensions", "operator"
        )
        self._validate_family_definition(manifest)
        config_dir, _ = definitions_directory(
            definition_family, config_root=self.config_dir, data_root=self.data_dir
        )
        if (config_dir / f"{local_id}.yaml").is_file():
            raise ValueError("an application definition owns this family and id")
        with self._lock:
            exists = path.is_file()
            if expected_fingerprint is not None:
                if not exists:
                    raise ValueError("the definition being edited no longer exists; reload before saving")
                current = parse_definition_manifest(
                    definition_family, path.read_text(encoding="utf-8"), str(path),
                    "data/extensions", "operator",
                )
                if definition_fingerprint(current) != expected_fingerprint:
                    raise ValueError(
                        "the definition changed since it was read; reload before saving"
                    )
            elif exists:
                raise ValueError(
                    f"an operator {family} definition with id '{local_id}' already exists; edit it instead of creating a new one"
                )
            path.parent.mkdir(parents=True, exist_ok=True)
            write_text_atomic(path, text)
            identifier = f"{family}:{local_id}"
            if family == "mcp":
                # A connection's shape (transport, url, allowlists) may have just changed, so a
                # cached discovery snapshot from the old definition must not be served as if it
                # still describes the current one - the same clearing delete_definition already
                # does, applied here because an edit can invalidate discovery just as removal does.
                self.snapshots.delete(identifier)
                self._snapshots.pop(identifier, None)
                # The open connection (if any) belongs to the definition that just changed -
                # a still-running process for the old command/URL must not keep serving
                # calls under a definition it no longer matches.
                self._sessions.close(identifier)
                self._mcp_call_context.pop(identifier, None)
            elif family == "acp":
                # Same reasoning as the mcp branch above: a still-running agent process
                # for the old argv/boundary must not keep serving prompts under a
                # definition it no longer matches. A remembered session id is tied to
                # the old command/argv too - resuming it against whatever the edit
                # points at now would not be resuming the same agent. ACP connection
                # ids are namespaced by host conversation too (`acp:{local_id}:{
                # session_id}`), so closing the one bare `identifier` would not match
                # any of them - close_prefix closes every conversation's connection
                # for this agent instead.
                self._sessions.close_prefix(f"{identifier}:")
                self._forget_acp_session_ids(identifier)
        self.actions.refresh()
        return {
            "extension_id": f"{family}:{local_id}",
            "source": str(path),
            "fingerprint": definition_fingerprint(manifest),
        }

    def delete_definition(self, family: str, local_id: str) -> dict[str, Any]:
        path = self._definition_path(family, local_id)
        if not path.is_file():
            raise ValueError("unknown operator definition")
        path.unlink()
        identifier = f"{family}:{local_id}"
        if family == "mcp":
            self.snapshots.delete(identifier)
            self._snapshots.pop(identifier, None)
            self._sessions.close(identifier)
            self._mcp_call_context.pop(identifier, None)
        elif family == "acp":
            self._sessions.close_prefix(f"{identifier}:")
            self._forget_acp_session_ids(identifier)
        self.actions.refresh()
        return {"extension_id": identifier, "removed": True}

    def _forget_acp_session_ids(self, identifier: str) -> None:
        """Drops every remembered resume session id for `identifier` (`acp:{local_id}`),
        across all host conversations - keys are `{identifier}:{operation.session_id}`.
        """
        prefix = f"{identifier}:"
        for key in [key for key in self._acp_session_ids if key.startswith(prefix)]:
            self._acp_session_ids.pop(key, None)

    def _validate_family_definition(self, manifest: DefinitionManifest) -> None:
        """Run the family's own contract so an invalid definition never reaches disk."""
        if manifest.family == "mcp":
            from backend.app.extensions.mcp import McpConnectionDefinition

            McpConnectionDefinition.from_mapping(manifest.local_id, manifest.definition)
        elif manifest.family == "acp":
            from backend.app.extensions.acp import AcpDefinition

            AcpDefinition.from_mapping(manifest.local_id, manifest.definition)
        else:
            # tool, hook, and plugin contracts are enforced when their operations are built.
            for _ in self._operations_for(manifest):
                break

    def write_skill(self, local_id: str, body: str) -> dict[str, Any]:
        """Create or replace an operator-owned skill.

        The manifest is parsed before it is written, so a skill that declares authority or
        malformed frontmatter is refused with its reason instead of landing on disk and
        failing at discovery.
        """
        from backend.app.extensions.skills import (
            SKILL_MANIFEST,
            operator_skills_directory,
            parse_skill_frontmatter,
        )

        if not SAFE_LOCAL_ID.match(local_id):
            raise ValueError(f"id must match {SAFE_LOCAL_ID.pattern}")
        parse_skill_frontmatter(local_id, body, f"data/extensions/skills/{local_id}")
        application = (
            self.config_dir / "extensions" / "skills" / local_id / SKILL_MANIFEST
        )
        if application.is_file():
            raise ValueError("an application skill owns this id")
        directory = operator_skills_directory(self.data_dir) / local_id
        directory.mkdir(parents=True, exist_ok=True)
        (directory / SKILL_MANIFEST).write_text(body, encoding="utf-8")
        self.actions.refresh()
        return {"extension_id": f"skill:{local_id}", "source": str(directory / SKILL_MANIFEST)}

    def delete_skill(self, local_id: str) -> dict[str, Any]:
        from backend.app.extensions.skills import SKILL_MANIFEST, operator_skills_directory

        if not SAFE_LOCAL_ID.match(local_id):
            raise ValueError(f"id must match {SAFE_LOCAL_ID.pattern}")
        manifest = operator_skills_directory(self.data_dir) / local_id / SKILL_MANIFEST
        if not manifest.is_file():
            raise ValueError("unknown operator skill")
        manifest.unlink()
        directory = manifest.parent
        if not any(directory.iterdir()):
            directory.rmdir()
        self.actions.refresh()
        return {"extension_id": f"skill:{local_id}", "removed": True}

    def oauth_status(self, extension_id: str) -> dict[str, Any]:
        """Report whether an MCP connection is OAuth-configured and currently authorized."""
        from backend.app.extensions.mcp import McpConnectionDefinition
        from backend.app.extensions.mcp_oauth import load_oauth_token

        manifest = next(
            (item for item in self.definitions()
             if f"{item.family}:{item.local_id}" == extension_id and item.family == "mcp"),
            None,
        )
        if manifest is None:
            raise ValueError("unknown MCP connection")
        definition = McpConnectionDefinition.from_mapping(manifest.local_id, manifest.definition)
        if definition.oauth is None:
            return {"extension_id": extension_id, "configured": False, "authorized": False}
        token = load_oauth_token(self.runs.store, manifest.local_id)
        return {
            "extension_id": extension_id,
            "configured": True,
            "authorized": token is not None and not token.is_expired(),
            "expires_at": token.expires_at if token else None,
        }

    def oauth_authorize(self, extension_id: str) -> dict[str, Any]:
        """Begin an OAuth authorization and return the URL the operator must visit.

        The verifier and state stay on the backend; the desktop only ever sees the URL.
        """
        from backend.app.extensions.mcp import McpConnectionDefinition
        from backend.app.extensions.mcp_oauth import McpOAuthFlow, config_from_definition

        manifest = next(
            (item for item in self.definitions()
             if f"{item.family}:{item.local_id}" == extension_id and item.family == "mcp"),
            None,
        )
        if manifest is None:
            raise ValueError("unknown MCP connection")
        definition = McpConnectionDefinition.from_mapping(manifest.local_id, manifest.definition)
        if definition.oauth is None:
            raise ValueError("this MCP connection is not configured for OAuth")
        config = config_from_definition(definition.oauth, resource_url=definition.url)
        flow = McpOAuthFlow(config)
        url, state = flow.start_authorization()
        with self._lock:
            self._oauth_flows[extension_id] = (flow, state)
        return {"extension_id": extension_id, "authorization_url": url, "state": state}

    def oauth_complete(self, extension_id: str, code: str, state: str) -> dict[str, Any]:
        """Exchange an authorization code and store the token in the secret store."""
        from backend.app.extensions.mcp_oauth import save_oauth_token

        with self._lock:
            pending = self._oauth_flows.pop(extension_id, None)
        if pending is None:
            raise ValueError("no authorization is in progress for this connection")
        flow, expected_state = pending
        if state != expected_state:
            raise ValueError("authorization state does not match the request")
        token = flow.exchange_code(code, state)
        save_oauth_token(self.runs.store, extension_id.split(":", 1)[1], token)
        return {"extension_id": extension_id, "authorized": True}

    def oauth_forget(self, extension_id: str) -> dict[str, Any]:
        """Clear a connection's stored OAuth authorization and close its live session.

        The MCP authorization specification (2026-07-28) defines no revocation or logout
        flow and says nothing about a client's responsibility when it stops using a
        token; it profiles OAuth 2.1, RFC 6750, RFC 7591, RFC 8414, RFC 8707, RFC 9728,
        RFC 9207, OAuth Client ID Metadata Documents, and OpenID Connect Discovery, none
        of which this method needs. Deleting the client's own stored copy is sufficient
        for the authorization server's own governance of the token; it is not sufficient
        on its own for "the next operation refuses with not authorized" to actually be
        true here, because `mcp_credentials` only resolves a bearer header once, when a
        connection first opens, and the resource then keeps using that same header for
        every call against it afterward - a still-open connection from before this call
        would otherwise keep authorizing successfully with the now-forgotten credentials
        until it happened to die on its own for an unrelated reason. Closing the session
        is what forces the next operation to open fresh and re-resolve credentials that
        are no longer there. This is why oauth_forget also closes the session, unlike
        `disconnect` (ending an active connection without touching stored authorization).
        """
        from backend.app.extensions.mcp import McpConnectionDefinition
        from backend.app.extensions.mcp_oauth import OAUTH_SECRET_NAME, oauth_owner_id

        manifest = next(
            (item for item in self.definitions()
             if f"{item.family}:{item.local_id}" == extension_id and item.family == "mcp"),
            None,
        )
        if manifest is None:
            raise ValueError("unknown MCP connection")
        definition = McpConnectionDefinition.from_mapping(manifest.local_id, manifest.definition)
        if definition.oauth is None:
            raise ValueError("this MCP connection is not configured for OAuth")
        self.runs.store.delete_secret(oauth_owner_id(manifest.local_id), OAUTH_SECRET_NAME)
        confirmed = self._sessions.close(extension_id)
        self._mcp_call_context.pop(extension_id, None)
        with self._lock:
            self._oauth_flows.pop(extension_id, None)
        if not confirmed:
            raise ValueError(
                "Stored authorization was removed locally, but the connection could not be "
                "confirmed closed and may still be running."
            )
        return {"extension_id": extension_id, "authorized": False}

    def disconnect(self, extension_id: str) -> dict[str, Any]:
        """Ends an MCP connection's open stdio/streamable-http session on operator
        request, without touching its definition, stored credentials, or authorization.

        `oauth_forget` removes local authorization and closes the cached connection;
        `extension-state-update` changes enablement and closes through ExtensionService.
        Disconnect preserves authorization and enablement, so the connection
        simply reopens a fresh session on its next call, the same way it does after an
        unexpected process death.

        Raises if teardown could not be confirmed, rather than reporting
        `connected: False` regardless - a probe reproduced this call returning as if it
        had succeeded while the underlying process was still alive. The caller (the
        operator route, via `execute_operator_action`) already turns a raised
        `ValueError` into a failed execution record instead of a silent success.
        """
        manifest = next(
            (item for item in self.definitions()
             if f"{item.family}:{item.local_id}" == extension_id and item.family == "mcp"),
            None,
        )
        if manifest is None:
            raise ValueError("unknown MCP connection")
        identifier = f"mcp:{manifest.local_id}"
        confirmed = self._sessions.close(identifier)
        self._mcp_call_context.pop(identifier, None)
        if not confirmed:
            raise ValueError(
                f"could not confirm the connection for '{extension_id}' actually closed; "
                "it may still be running"
            )
        return {"extension_id": extension_id, "connected": False}

    def close_session(self, extension_id: str) -> bool:
        """Ends any open MCP/ACP session for `extension_id`, if one exists.

        Called when an extension leaves the "enabled" state (`extension-state-update`
        to disabled/retired): a still-running connection must not keep serving calls for
        a definition the operator just turned off - the same requirement
        `write_definition`/`delete_definition` already enforce for a changed or removed
        definition, applied here for a state change instead. Safe to call for a family
        with no session concept (prompt, skill, tool, hook) or an identifier with no
        open connection - both are no-ops and report `True`.

        Returns whether teardown was actually confirmed, so a caller (`ExtensionService.
        set_state`) can propagate a failure instead of asserting the state change fully
        succeeded when the underlying connection may still be alive.
        """
        family = extension_id.split(":", 1)[0]
        if family == "mcp":
            confirmed = self._sessions.close(extension_id)
            self._mcp_call_context.pop(extension_id, None)
            return confirmed
        if family == "acp":
            return self._sessions.close_prefix(f"{extension_id}:")
        return True

    def mcp_credentials(self, definition: Any, local_id: str) -> dict[str, str]:
        """Resolve host-owned credentials for one MCP connection."""
        if definition.oauth is not None:
            from backend.app.extensions.mcp_oauth import resolve_oauth_bearer

            access = resolve_oauth_bearer(
                self.runs.store, local_id, definition.oauth, resource_url=definition.url,
            )
            return {"Authorization": f"Bearer {access}"}
        if not definition.credential_ref:
            return {}
        value = self.runs.store.read_secret(f"extension:mcp:{local_id}", definition.credential_ref)
        if value is None:
            raise ValueError("MCP credential is unavailable")
        if definition.transport == "stdio":
            # scrub_environment is an allowlist, so a credential the connection does not pass
            # through is dropped silently and the server would start unauthenticated.
            if definition.credential_ref not in definition.process_boundary.env_passthrough:
                raise ValueError(
                    "MCP credential is not listed in the connection's env_passthrough; "
                    "the server would start without it"
                )
            return {definition.credential_ref: value}
        return {"Authorization": f"Bearer {value}"}

    def detail(self, extension_id: str) -> dict[str, Any]:
        self.actions.refresh()
        return {
            "extension_id": extension_id, "operations": self._operations.get(extension_id, []),
            "snapshot": self._snapshots.get(extension_id), "error": self._errors.get(extension_id),
            # `snapshot.health` is a cached fact from the last discover call, not a live
            # read - a probe reproduced it still reporting "ready" after Disconnect
            # closed the session, with nothing in the response distinguishing history
            # from the current state. `is_open` is safe to call for any identifier
            # (including one with no session concept, or one never opened) - reports
            # `False` rather than raising.
            "connected": self._sessions.is_open(extension_id),
        }

    def observation(self) -> tuple:
        from backend.app.extensions.discovery import DefinitionError, DefinitionRuntime
        from backend.app.extensions.lifecycle import HookDefinition
        definitions = self.definitions()
        records = []
        for manifest in definitions:
            identifier = f"{manifest.family}:{manifest.local_id}"
            error = self._errors.get(identifier)
            ready = bool(self._operations.get(identifier)) and not error
            if manifest.family == "hook":
                try:
                    data = manifest.definition
                    hook = HookDefinition(manifest.local_id, data["event"], data.get("effect_class", "local_read"), data.get("capability_id"))
                    target = self.actions.descriptor(hook.capability_id) if hook.capability_id else None
                    ready = bool((target and target.effect_class == hook.effect_class) or
                                 (not hook.capability_id and data.get("handler") == "record_event" and manifest.trust == "application"))
                except (KeyError, ValueError):
                    ready = False
            records.append(DefinitionRuntime(manifest.family, manifest.local_id,
                                             "ready" if ready else "unavailable", "available" if ready else "misconfigured",
                                             "" if ready else error or "Extension is not executable; inspect its definition and dependencies."))
        errors = tuple(DefinitionError(key.split(":", 1)[0], key, message) for key, message in {**self._errors, **self._load_errors}.items())
        return tuple(definitions), tuple(records), errors

    def tool_catalog(self) -> list[dict[str, Any]]:
        """Model-facing description of every extension operation, keyed by capability id.

        ACP operations are excluded: they execute through TurnEngine.run_extension, which
        re-acquires the single turn lock, so selecting one from inside a turn cannot run.
        ADR 0007 owns agent delegation.
        """
        self.actions.refresh()
        with self._lock:
            operations = {key: list(value) for key, value in self._operations.items()}
        catalog: list[dict[str, Any]] = []
        for identifier, items in sorted(operations.items()):
            if identifier.startswith(("acp:", "skill:")):
                continue
            for item in items:
                if not item["available"]:
                    continue
                catalog.append({
                    "capability_id": item["capability_id"],
                    "extension_id": identifier,
                    "name": item["name"],
                    "input_schema": item["input_schema"],
                })
        return catalog

    def executable_skills(self) -> list[str]:
        return [key.split(":", 1)[1] for key, operations in self._operations.items()
                if key.startswith("skill:") and any(item["available"] for item in operations)]

    def invoke(self, extension_id: str, capability_id: str, arguments: dict[str, Any]) -> Any:
        """Runs one extension operation on the operator's own direct request (the
        dedicated Invoke path, reached from `POST /extensions/{id}/invoke`).

        Goes through `CapabilityService.invoke_operator_capability` rather than the
        generic `propose()`/park surface: the operator already fully specified the
        capability and its arguments by invoking it here, so a `privileged_execution`/
        `destructive_action` capability executes immediately instead of parking for a
        second decision on a request that has already been made, the same self-approval
        `execute_operator_action` already gives `/memory`, `/config/llm`, and
        `/config/operator`. A *model*-proposed call against the same capability during a
        live conversation turn is a different call site entirely
        (`backend/app/conversation/engine.py`'s own `propose(..., proposed_by="model")`)
        and still parks for a separate operator decision.
        """
        detail = self.detail(extension_id)
        if capability_id not in {item["capability_id"] for item in detail["operations"]}:
            raise ValueError("operation does not belong to this extension")
        return self.actions.invoke_operator_capability(
            capability_id=capability_id, arguments=arguments,
            proposed_by="operator", reason=f"Invoke {extension_id}",
        )

    def answer(self, run_id: str, request_id: str, answer: dict[str, Any]) -> None:
        from backend.app.actions.contracts import validate_arguments
        request = self.runs.read(run_id).get("request")
        if not request or request.get("request_id") != request_id:
            raise ValueError("request is no longer pending")
        if request.get("kind") == "permission_request":
            offered = {item.get("optionId") for item in request.get("options", [])}
            if answer.get("action") == "accept" and answer.get("option_id") not in offered:
                raise ValueError("permission option was not offered")
        elif answer.get("action") == "accept":
            if validate_arguments(request.get("requestedSchema", {"type": "object"}), answer.get("content", {})):
                raise ValueError("elicitation response does not satisfy its schema")
        self.actions.execute_operator_action("extension-input-answer", {"run_id": run_id, "request_id": request_id},
                                             lambda: self.runs.answer(run_id, request_id, answer))

    def list_runs(self) -> list[dict[str, Any]]:
        owners = {operation["capability_id"]: identifier for identifier, operations in self._operations.items() for operation in operations}
        pending = [{"run_id": item.proposal_id, "extension_id": owners[item.capability_id],
                    "proposal_id": item.proposal_id, "status": "awaiting_approval", "events": [],
                    "request": None, "arguments": item.arguments, "reason": item.reason}
                   for item in self.actions.pending() if item.capability_id in owners]
        return pending + self.runs.list()

    def credential(self, extension_id: str, name: str, secret: str) -> None:
        if not any(f"{item.family}:{item.local_id}" == extension_id for item in self.definitions()):
            raise ValueError("unknown extension")
        self.actions.execute_operator_action("extension-credential-write", {"extension_id": extension_id, "name": name},
                                             lambda: self.runs.store.write_secret(f"extension:{extension_id}", name, secret))

    def close(self) -> None:
        for run in self.runs.list():
            if run["status"] in {"running", "awaiting_input"}:
                self.actions.cancel(run["proposal_id"])
        self._sessions.shutdown()
