from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

_ALLOWED_FIELDS = {
    "profile_id",
    "display_name",
    "description",
    "locale",
    "system",
    "style",
    "traits",
    "examples",
    "generation",
    "enabled",
}

_PROHIBITED_FIELDS = {
    "tool_permissions",
    "tool_policy",
    "routing_policy",
    "model_routing",
    "memory_policy",
    "memory_permissions",
    "safety_overrides",
    "hidden_instructions",
}

_SAFE_PROFILE_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_TRAIT_LEVELS = {"none", "low", "medium", "high", "strong"}
_HUMOR_LEVELS = {"none", "light", "medium", "high", "dry"}
_TRAIT_FIELDS = {"warmth", "assertiveness", "detail", "humor"}


@dataclass(frozen=True, slots=True)
class PersonalityStyle:
    max_words_default: int
    structure: str
    do: tuple[str, ...] = field(default_factory=tuple)
    avoid: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.max_words_default, int) or self.max_words_default <= 0:
            raise ValueError("style.max_words_default must be a positive integer")
        _validate_non_empty_string("style.structure", self.structure)
        _validate_string_list("style.do", self.do)
        _validate_string_list("style.avoid", self.avoid)


@dataclass(frozen=True, slots=True)
class PersonalityExample:
    user: str
    assistant: str

    def __post_init__(self) -> None:
        _validate_non_empty_string("examples.user", self.user)
        _validate_non_empty_string("examples.assistant", self.assistant)

    def to_messages(self) -> tuple[dict[str, str], dict[str, str]]:
        return (
            {"role": "user", "content": self.user},
            {"role": "assistant", "content": self.assistant},
        )


@dataclass(frozen=True, slots=True)
class PersonalityTraits:
    warmth: str
    assertiveness: str
    detail: str
    humor: str

    def __post_init__(self) -> None:
        _validate_member("traits.warmth", self.warmth, _TRAIT_LEVELS)
        _validate_member("traits.assertiveness", self.assertiveness, _TRAIT_LEVELS)
        _validate_member("traits.detail", self.detail, _TRAIT_LEVELS)
        _validate_member("traits.humor", self.humor, _HUMOR_LEVELS)


@dataclass(frozen=True, slots=True)
class PersonalityProfile:
    profile_id: str
    display_name: str
    description: str
    locale: str
    system: str
    style: PersonalityStyle
    traits: PersonalityTraits
    examples: tuple[PersonalityExample, ...]
    generation: dict[str, Any]
    enabled: bool = True

    def __post_init__(self) -> None:
        _validate_profile_id(self.profile_id)
        _validate_non_empty_string("display_name", self.display_name)
        _validate_non_empty_string("description", self.description)
        _validate_non_empty_string("locale", self.locale)
        _validate_non_empty_string("system", self.system)
        if not isinstance(self.style, PersonalityStyle):
            raise ValueError("style must be a mapping")
        if not isinstance(self.traits, PersonalityTraits):
            raise ValueError("traits must be a mapping")
        if not isinstance(self.examples, tuple) or not self.examples:
            raise ValueError("examples must be a non-empty list")
        if any(not isinstance(item, PersonalityExample) for item in self.examples):
            raise ValueError("examples must contain user/assistant mappings")
        if not isinstance(self.enabled, bool):
            raise ValueError("enabled must be a boolean")
        _validate_generation(self.generation)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PersonalityProfile:
        _reject_unknown_or_prohibited_fields(data)
        required = _ALLOWED_FIELDS - {"enabled"}
        missing = sorted(field_name for field_name in required if field_name not in data)
        if missing:
            raise ValueError(f"personality profile missing required fields: {', '.join(missing)}")
        return cls(
            profile_id=_coerce_non_empty_string("profile_id", data["profile_id"]),
            display_name=_coerce_non_empty_string("display_name", data["display_name"]),
            description=_coerce_non_empty_string("description", data["description"]),
            locale=_coerce_non_empty_string("locale", data["locale"]),
            system=_coerce_non_empty_string("system", data["system"]),
            style=_coerce_style(data["style"]),
            traits=_coerce_traits(data["traits"]),
            examples=_coerce_examples(data["examples"]),
            generation=_coerce_generation(data["generation"]),
            enabled=_coerce_enabled(data.get("enabled", True)),
        )


def _reject_unknown_or_prohibited_fields(data: dict[str, Any]) -> None:
    unexpected = set(data) - _ALLOWED_FIELDS
    prohibited = set(data) & _PROHIBITED_FIELDS
    if prohibited:
        names = ", ".join(sorted(prohibited))
        raise ValueError(f"personality profile contains prohibited authority fields: {names}")
    if unexpected:
        names = ", ".join(sorted(unexpected))
        raise ValueError(f"personality profile contains unknown fields: {names}")


def _validate_profile_id(value: str) -> None:
    _validate_non_empty_string("profile_id", value)
    if not _SAFE_PROFILE_ID_RE.fullmatch(value):
        raise ValueError("profile_id must contain lowercase letters, numbers, hyphens, or underscores")


def _validate_non_empty_string(field_name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _coerce_non_empty_string(field_name: str, value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a non-empty string")
    text = value.strip()
    _validate_non_empty_string(field_name, text)
    return text


def _validate_member(field_name: str, value: str, allowed: set[str]) -> None:
    if value not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise ValueError(f"invalid personality {field_name}: {value!r}; expected one of: {allowed_values}")


def _coerce_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    raise ValueError("enabled must be a boolean")


def _validate_string_list(field_name: str, value: tuple[str, ...]) -> None:
    if not isinstance(value, tuple) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValueError(f"{field_name} must be a list of non-empty strings")


def _coerce_string_list(field_name: str, value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str) or not isinstance(value, list | tuple):
        raise ValueError(f"{field_name} must be a list of non-empty strings")
    coerced = tuple(str(item) for item in value)
    _validate_string_list(field_name, coerced)
    return coerced


def _coerce_style(value: Any) -> PersonalityStyle:
    if not isinstance(value, dict):
        raise ValueError("style must be a mapping")
    unexpected = set(value) - {"max_words_default", "structure", "do", "avoid"}
    if unexpected:
        raise ValueError(f"style contains unknown fields: {', '.join(sorted(unexpected))}")
    for key in ("max_words_default", "structure", "do", "avoid"):
        if key not in value:
            raise ValueError(f"style.{key} is required")
    return PersonalityStyle(
        max_words_default=value["max_words_default"],
        structure=_coerce_non_empty_string("style.structure", value["structure"]),
        do=_coerce_string_list("style.do", value["do"]),
        avoid=_coerce_string_list("style.avoid", value["avoid"]),
    )


def _coerce_traits(value: Any) -> PersonalityTraits:
    if not isinstance(value, dict):
        raise ValueError("traits must be a mapping")
    unexpected = set(value) - _TRAIT_FIELDS
    if unexpected:
        raise ValueError(f"traits contains unknown fields: {', '.join(sorted(unexpected))}")
    missing = sorted(_TRAIT_FIELDS - set(value))
    if missing:
        raise ValueError(f"traits missing required fields: {', '.join(missing)}")
    return PersonalityTraits(
        warmth=_coerce_non_empty_string("traits.warmth", value["warmth"]),
        assertiveness=_coerce_non_empty_string("traits.assertiveness", value["assertiveness"]),
        detail=_coerce_non_empty_string("traits.detail", value["detail"]),
        humor=_coerce_non_empty_string("traits.humor", value["humor"]),
    )


def _coerce_examples(value: Any) -> tuple[PersonalityExample, ...]:
    if not isinstance(value, list | tuple) or not value:
        raise ValueError("examples must be a non-empty list")
    examples: list[PersonalityExample] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"examples[{index}] must be a mapping")
        unexpected = set(item) - {"user", "assistant"}
        if unexpected:
            raise ValueError(f"examples[{index}] contains unknown fields: {', '.join(sorted(unexpected))}")
        if "user" not in item or "assistant" not in item:
            raise ValueError(f"examples[{index}] must include user and assistant")
        examples.append(
            PersonalityExample(
                user=_coerce_non_empty_string(f"examples[{index}].user", item["user"]),
                assistant=_coerce_non_empty_string(f"examples[{index}].assistant", item["assistant"]),
            )
        )
    return tuple(examples)


def _coerce_generation(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("generation must be a mapping")
    coerced = dict(value)
    _validate_generation(coerced)
    return coerced


def _validate_generation(value: dict[str, Any]) -> None:
    allowed = {"temperature", "top_p", "top_k", "repeat_penalty", "max_tokens", "stop"}
    unexpected = set(value) - allowed
    if unexpected:
        raise ValueError(f"generation contains unknown fields: {', '.join(sorted(unexpected))}")
    for key in ("temperature", "top_p", "repeat_penalty"):
        if key not in value or not isinstance(value[key], int | float):
            raise ValueError(f"generation.{key} must be numeric")
    for key in ("top_k", "max_tokens"):
        if key not in value or not isinstance(value[key], int) or value[key] <= 0:
            raise ValueError(f"generation.{key} must be a positive integer")
    if "stop" not in value:
        raise ValueError("generation.stop must be a list of strings")
    stop = value["stop"]
    if not isinstance(stop, list | tuple) or any(not isinstance(item, str) or not item for item in stop):
        raise ValueError("generation.stop must be a list of strings")
