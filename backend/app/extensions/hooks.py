from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import asdict
from typing import Any

from backend.app.artifacts.storage import append_action_event
from backend.app.extensions.discovery import DefinitionManifest
from backend.app.extensions.lifecycle import HOOK_EVENTS, HookDefinition
from backend.app.services.capability_service import CapabilityService


class HookRunner:
    def __init__(self, actions: CapabilityService, definitions: Callable[[], list[DefinitionManifest]]) -> None:
        self.actions = actions
        self.definitions = definitions
        self._active = threading.local()

    def emit(self, event: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        if event not in HOOK_EVENTS:
            raise ValueError("unknown hook event")
        if getattr(self._active, "running", False):
            return []
        self._active.running = True
        results = []
        try:
            for manifest in sorted(self.definitions(), key=lambda item: item.local_id):
                if manifest.family != "hook" or not manifest.declared_enabled:
                    continue
                definition = manifest.definition
                if definition.get("event") != event:
                    continue
                try:
                    hook = HookDefinition(
                        manifest.local_id, event, definition.get("effect_class", "local_read"),
                        definition.get("capability_id"),
                    )
                    if hook.capability_id:
                        target = self.actions.descriptor(hook.capability_id)
                        if target is None or target.effect_class != hook.effect_class:
                            raise ValueError("hook effect must match its registered capability")
                        view = self.actions.propose(
                            capability_id=hook.capability_id,
                            arguments=definition.get("arguments", {}),
                            proposed_by=f"hook:{hook.hook_id}", reason=f"Lifecycle event: {event}",
                            session_id=str(context.get("session_id", "api")),
                            turn_id=context.get("turn_id"), caller="hook",
                        )
                        results.append({"hook_id": hook.hook_id, "event": event, "action": asdict(view)})
                    elif definition.get("handler") == "record_event" and manifest.trust == "application":
                        results.append({"hook_id": hook.hook_id, "event": event, "status": "observed"})
                    else:
                        raise ValueError("inline hooks require an application-owned record_event handler")
                except Exception:
                    results.append({"hook_id": manifest.local_id, "event": event, "status": "failure"})
            for record in results:
                append_action_event({"kind": "hook_event", "record": record, **context})
            return results
        finally:
            self._active.running = False
