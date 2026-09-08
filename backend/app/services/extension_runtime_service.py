from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import threading
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

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
from backend.app.core.paths import CONFIG_DIR, DATA_DIR
from backend.app.extensions.discovery import (
    DEFINITION_FAMILIES,
    DefinitionManifest,
    discover_definition_manifests,
)
from backend.app.extensions.hooks import HookRunner
from backend.app.extensions.runs import ExtensionRuns
from backend.app.extensions.skills import resolve_skill_script
from backend.app.extensions.store import ExtensionOverlayStore
from backend.app.services.capability_service import CapabilityService

ENDPOINT_ONLY_CAPABILITIES = {
    "extension-input-answer": "backend.app.api.routes.extensions.answer_extension_input",
    "extension-credential-write": "backend.app.api.routes.extensions.write_extension_credential",
}


def operation_id(extension_id: str, name: str) -> str:
    digest = hashlib.sha256(f"{extension_id}:{name}".encode()).hexdigest()[:24]
    return f"extension-{digest}"


def _authorization_for(family: str, effect_class: str) -> str:
    # Installing a plugin only writes under data/, but it places new executable definitions on
    # the host that then register privileged capabilities, which the effect class cannot express.
    if family == "plugin":
        return "requires_approval"
    return default_authorization(effect_class)


class ExtensionRuntimeService:
    def __init__(self, actions: CapabilityService, *, config_dir: Path | None = None,
                 data_dir: Path | None = None, db_path: Path | None = None) -> None:
        self.actions = actions
        self.config_dir = config_dir or CONFIG_DIR
        self.data_dir = data_dir or DATA_DIR
        self.overlay = ExtensionOverlayStore(db_path)
        self.runs = ExtensionRuns(db_path)
        self.hooks = HookRunner(actions, self.definitions)
        self._snapshots: dict[str, dict[str, Any]] = {}
        self._operations: dict[str, list[dict[str, Any]]] = {}
        self._errors: dict[str, str] = {}
        self._load_errors: dict[str, str] = {}
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
                        authorization_rule=_authorization_for(manifest.family, effect),
                        execution_owner="backend.extension_runtime",
                        timeout_policy={"timeout_ms": 60000}, cancellation_policy={"cancellable": True},
                        result_schema={"type": "object"}, artifact_evidence={"records": True},
                        unavailable_explanation="" if manifest.declared_enabled else "Extension is disabled.",
                        boundaries=boundary,
                        metadata_claims={"definition": {"sha256": hashlib.sha256(fingerprint.encode()).hexdigest(), "trusted": False}},
                    )
                    bindings.append((descriptor, self._handler(manifest, name, handler)))
                    operations.setdefault(identifier, []).append({"name": name, "capability_id": descriptor.capability_id,
                                                                "input_schema": schema, "available": manifest.declared_enabled})
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
        effect = "privileged_execution" if connection.transport == "stdio" else "external_read"
        operations = [("discover", empty, effect, lambda args, op, run: self._mcp(manifest, "discover", args, op, run))]
        snapshot = self._snapshots.get(identifier, {})
        for tool in snapshot.get("tools", []):
            name = "tool:" + tool["name"]
            operations.append((name, tool["inputSchema"], effect if effect == "privileged_execution" else "external_write",
                               lambda args, op, run, name=name: self._mcp(manifest, name, args, op, run)))
        for resource in snapshot.get("resources", []):
            name = "resource:" + resource["uri"]
            operations.append((name, empty, effect, lambda args, op, run, name=name: self._mcp(manifest, name, args, op, run)))
        for prompt in snapshot.get("prompts", []):
            name = "prompt:" + prompt["name"]
            fields = prompt.get("arguments", [])
            schema = {"type": "object", "properties": {item["name"]: {"type": "string"} for item in fields},
                      "required": [item["name"] for item in fields if item.get("required")], "additionalProperties": False}
            operations.append((name, schema, effect, lambda args, op, run, name=name: self._mcp(manifest, name, args, op, run)))
        return operations

    def _handler(self, manifest: DefinitionManifest, name: str, handler: Callable) -> Callable:
        def execute(arguments: dict[str, Any], operation: ActionOperation) -> dict[str, Any]:
            def work() -> dict[str, Any]:
                identifier = f"{manifest.family}:{manifest.local_id}"
                current = next((item for item in self.definitions() if f"{item.family}:{item.local_id}" == identifier), None)
                if current is None or not current.declared_enabled or current.definition != manifest.definition:
                    raise ValueError("extension definition changed or was disabled")
                run_id = self.runs.create(identifier, operation)
                try:
                    result = handler(arguments, operation, run_id)
                    operation.check()
                    result = bound_result(result, operation.boundary.max_result_bytes, {})
                    self.runs.update(run_id, status="success", result=result)
                    return {"run_id": run_id, "output": result}
                except ActionCancelledError:
                    self.runs.update(run_id, status="cancelled", request=None)
                    raise
                except Exception as exc:
                    self.runs.update(run_id, status="failure", request=None)
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
        return run_acp(
            AcpDefinition.from_mapping(manifest.local_id, manifest.definition), arguments["prompt"], operation,
            on_event=lambda event: self.runs.event(run_id, event),
            request_permission=lambda request: self.runs.request(run_id, {"kind": "permission", **request}, operation),
        )

    def _mcp(self, manifest: DefinitionManifest, name: str, arguments: dict[str, Any], operation: ActionOperation, run_id: str) -> dict[str, Any]:
        from backend.app.extensions.mcp import (
            McpConnectionDefinition,
            McpConnectionRuntime,
            McpHostCallbacks,
            open_mcp_sdk_peer,
        )
        definition = McpConnectionDefinition.from_mapping(manifest.local_id, manifest.definition)
        async def credentials(_definition: Any) -> dict[str, str]:
            return self.mcp_credentials(definition, manifest.local_id)
        async def authorize(op: ActionOperation, kind: str, request: dict[str, Any]) -> None:
            op.check()
        async def elicit(_definition: Any, request: dict[str, Any]) -> dict[str, Any]:
            return await asyncio.to_thread(self.runs.request, run_id, {"kind": "elicitation", **request}, operation)
        async def invoke() -> dict[str, Any]:
            runtime = McpConnectionRuntime(definition, peer_factory=open_mcp_sdk_peer,
                                           callbacks=McpHostCallbacks(credentials, authorize, elicit))
            try:
                if name == "discover":
                    snapshot = (await runtime.refresh(operation)).to_dict()
                    self._snapshots[f"mcp:{manifest.local_id}"] = snapshot
                    if snapshot.get("health") != "ready":
                        raise ValueError("MCP discovery failed")
                    return snapshot
                kind, value = name.split(":", 1)
                if kind == "tool":
                    result = await runtime.call_tool(operation, value, arguments)
                elif kind == "resource":
                    result = await runtime.read_resource(operation, value)
                else:
                    result = await runtime.get_prompt(operation, value, arguments)
                if hasattr(result, "model_dump"):
                    result = result.model_dump(mode="json", by_alias=True)
                return {"content": result, "trusted": False}
            finally:
                await runtime.close()
        return asyncio.run(invoke())

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
        return {"extension_id": extension_id, "operations": self._operations.get(extension_id, []),
                "snapshot": self._snapshots.get(extension_id), "error": self._errors.get(extension_id)}

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

    def executable_skills(self) -> list[str]:
        return [key.split(":", 1)[1] for key, operations in self._operations.items()
                if key.startswith("skill:") and any(item["available"] for item in operations)]

    def invoke(self, extension_id: str, capability_id: str, arguments: dict[str, Any]) -> Any:
        detail = self.detail(extension_id)
        if capability_id not in {item["capability_id"] for item in detail["operations"]}:
            raise ValueError("operation does not belong to this extension")
        return self.actions.propose(capability_id=capability_id, arguments=arguments,
                                    proposed_by="operator", reason=f"Invoke {extension_id}")

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
