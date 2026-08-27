from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass

from backend.app.cognition.prompt_envelope import PromptEnvelope
from backend.app.runtimes.llm.base import LLMBase
from backend.app.runtimes.llm.provider_runtime import ProviderRequestError
from backend.app.services.llm_provider_profiles import ProviderProfile, ProviderSelection

_CLOUD_REQUEST = re.compile(
    r"\b(?:use\s+(?:the\s+)?cloud|escalate\s+(?:this|that|the\s+request)|ask\s+(?:openai|claude|anthropic))\b",
    re.IGNORECASE,
)
_NEGATED_CLOUD_REQUEST = re.compile(
    r"\b(?:do\s+not|don't|never|without)\b.{0,40}\b(?:cloud|escalat|openai|claude|anthropic)\b",
    re.IGNORECASE,
)
_QUOTED_DISCUSSION = re.compile(r"\b(?:say|quote|phrase|means?|example)\b.{0,40}\b(?:use cloud|escalate this|ask claude)\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class ProviderAttempt:
    profile_id: str
    profile_name: str
    provider_kind: str
    trigger: str
    outcome: str
    duration_ms: float
    reason: str | None = None
    usage: dict[str, int] | None = None


class RoutedLLM(LLMBase):
    def __init__(
        self,
        *,
        profiles: dict[str, ProviderProfile],
        runtimes: dict[str, LLMBase],
        selection: ProviderSelection,
    ) -> None:
        self.profiles = profiles
        self.runtimes = runtimes
        self.selection = selection
        self.last_attempts: list[ProviderAttempt] = []
        self.reason = "not probed"

    def runtime_name(self) -> str:
        return self.runtimes[self.selection.primary_profile_id].runtime_name()

    def context_window(self) -> int:
        return self.runtimes[self.selection.primary_profile_id].context_window()

    def is_available(self) -> bool:
        runtime = self.runtimes[self.selection.primary_profile_id]
        available = runtime.is_available()
        self.reason = getattr(runtime, "reason", "ready" if available else "unavailable")
        return available

    def generate(self, prompt: str, **kwargs: object) -> str:
        from backend.app.cognition.prompt_envelope import PromptSegment

        return self.generate_envelope(
            PromptEnvelope((PromptSegment("user", "user_input", False, prompt),)),
            **kwargs,
        )

    def generate_envelope(self, envelope: PromptEnvelope, **kwargs: object) -> str:
        return self._execute(envelope, lambda runtime: runtime.generate_envelope(envelope, **kwargs))

    def generate_structured(self, envelope: PromptEnvelope, schema: dict[str, object]) -> str:
        return self._execute(envelope, lambda runtime: runtime.generate_structured(envelope, schema))

    def evidence(self) -> dict[str, object]:
        return {
            "primary_profile_id": self.selection.primary_profile_id,
            "cloud_escalation_enabled": self.selection.cloud_escalation_enabled,
            "attempts": [asdict(attempt) for attempt in self.last_attempts],
        }

    def _execute(self, envelope: PromptEnvelope, invoke: Callable[[LLMBase], str]) -> str:
        self.last_attempts = []
        explicit_cloud = self._explicit_cloud_request(envelope)
        if explicit_cloud:
            target = self._explicit_cloud_target(envelope)
            return self._attempt(target, "explicit_request", invoke)

        candidates: list[tuple[str, str]] = [(self.selection.primary_profile_id, "primary")]
        if self.selection.local_fallback_profile_id:
            candidates.append((self.selection.local_fallback_profile_id, "local_fallback"))
        if self.selection.cloud_escalation_enabled and self.selection.cloud_profile_id:
            candidates.append((self.selection.cloud_profile_id, "failure_escalation"))

        last_error: Exception | None = None
        for index, (profile_id, trigger) in enumerate(candidates):
            try:
                return self._attempt(profile_id, trigger, invoke)
            except Exception as exc:
                last_error = exc
                if not self._eligible_failure(exc):
                    raise
                remaining = candidates[index + 1 :]
                if not remaining:
                    raise
        assert last_error is not None
        raise last_error

    def _attempt(self, profile_id: str, trigger: str, invoke: Callable[[LLMBase], str]) -> str:
        profile = self.profiles[profile_id]
        runtime = self.runtimes[profile_id]
        started = time.perf_counter()
        try:
            response = invoke(runtime)
        except Exception as exc:
            self.last_attempts.append(
                ProviderAttempt(
                    profile.profile_id,
                    profile.name,
                    profile.kind,
                    trigger,
                    "failed",
                    (time.perf_counter() - started) * 1000.0,
                    reason=self._safe_reason(exc),
                )
            )
            raise
        usage = getattr(runtime, "last_usage", None)
        self.last_attempts.append(
            ProviderAttempt(
                profile.profile_id,
                profile.name,
                profile.kind,
                trigger,
                "succeeded",
                (time.perf_counter() - started) * 1000.0,
                usage=dict(usage) if isinstance(usage, dict) else None,
            )
        )
        return response

    def _explicit_cloud_request(self, envelope: PromptEnvelope) -> bool:
        user_text = self._user_text(envelope)
        if _NEGATED_CLOUD_REQUEST.search(user_text) or _QUOTED_DISCUSSION.search(user_text):
            return False
        if _CLOUD_REQUEST.search(user_text):
            return True
        for profile_id in {
            self.selection.primary_profile_id,
            self.selection.cloud_profile_id,
        }:
            profile = self.profiles.get(profile_id or "")
            if not profile or not profile.cloud_eligible:
                continue
            name = re.escape(profile.name)
            if re.search(rf"\b(?:use|ask|send\s+to)\s+(?:the\s+)?{name}\b", user_text, re.IGNORECASE):
                return True
        return False

    def _explicit_cloud_target(self, envelope: PromptEnvelope) -> str:
        user_text = self._user_text(envelope)
        primary = self.profiles[self.selection.primary_profile_id]
        permitted = [primary] if primary.cloud_eligible else []
        if self.selection.cloud_escalation_enabled and self.selection.cloud_profile_id:
            configured = self.profiles[self.selection.cloud_profile_id]
            if configured.profile_id not in {profile.profile_id for profile in permitted}:
                permitted.append(configured)
        if not permitted:
            raise RuntimeError("cloud escalation is disabled; enable it in Model Providers")

        requested_kind = None
        if re.search(r"\b(?:ask|use)\s+openai\b", user_text, re.IGNORECASE):
            requested_kind = "openai"
        elif re.search(r"\b(?:ask|use)\s+(?:claude|anthropic)\b", user_text, re.IGNORECASE):
            requested_kind = "anthropic"
        if requested_kind:
            for profile in permitted:
                if profile.kind == requested_kind:
                    return profile.profile_id
            raise RuntimeError("the requested cloud provider is not configured for this session")

        for profile in permitted:
            name = re.escape(profile.name)
            if re.search(rf"\b(?:use|ask|send\s+to)\s+(?:the\s+)?{name}\b", user_text, re.IGNORECASE):
                return profile.profile_id
        if primary.cloud_eligible:
            return primary.profile_id
        assert self.selection.cloud_profile_id is not None
        return self.selection.cloud_profile_id

    @staticmethod
    def _user_text(envelope: PromptEnvelope) -> str:
        return "\n".join(
            segment.text for segment in envelope.segments if segment.authority == "user"
        )

    @staticmethod
    def _eligible_failure(exc: Exception) -> bool:
        if isinstance(exc, ProviderRequestError):
            return exc.escalation_eligible
        lowered = str(exc).casefold()
        blocked = (
            "authentication",
            "credential",
            "unauthorized",
            "forbidden",
            "context",
            "safety",
            "refusal",
            "invalid request",
            "http 400",
        )
        return not any(token in lowered for token in blocked)

    @staticmethod
    def _safe_reason(exc: Exception) -> str:
        if isinstance(exc, ProviderRequestError):
            return str(exc)
        text = str(exc)
        return text[:240] if text else type(exc).__name__
