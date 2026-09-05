from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from backend.app.core.paths import CONFIG_DIR

PROMPTS_DIRNAME = "prompts"
# A reusable prompt is a user-invoked start, never policy. Application, persona and output
# are the authority bands that carry instruction weight, so a template may not claim them.
ALLOWED_AUTHORITIES = ("user", "session")
_ALLOWED_FIELDS = {"prompt_id", "version", "title", "description", "body", "authority", "variables"}
_REQUIRED_FIELDS = {"prompt_id", "version", "title", "description", "body", "authority"}
_PROHIBITED_FIELDS = {
    "trusted", "authority_override", "tool_policy", "tool_permissions",
    "routing_policy", "memory_policy", "safety_overrides", "hidden_instructions",
}
_SAFE_PROMPT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_VARIABLE = re.compile(r"\{\{\s*([a-z0-9_]+)\s*\}\}")
MAX_BODY_CHARS = 8_000


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    prompt_id: str
    version: str
    title: str
    description: str
    body: str
    authority: str
    variables: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PromptTemplateError:
    prompt_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class PromptTemplateList:
    templates: list[PromptTemplate] = field(default_factory=list)
    errors: list[PromptTemplateError] = field(default_factory=list)


def prompts_directory(base_dir: Path | None = None) -> Path:
    return (base_dir or CONFIG_DIR) / PROMPTS_DIRNAME


def _prompt_path(prompt_id: str, base_dir: Path | None = None) -> Path:
    if prompt_id != prompt_id.strip() or any(token in prompt_id for token in ("/", "\\", "..")):
        raise ValueError(f"unsafe prompt id: {prompt_id}")
    return prompts_directory(base_dir) / f"{prompt_id}.yaml"


def parse_prompt_template(payload: Any) -> PromptTemplate:
    if not isinstance(payload, dict):
        raise ValueError("prompt template must be a mapping")
    prohibited = sorted(_PROHIBITED_FIELDS & set(payload))
    if prohibited:
        raise ValueError(
            f"prompt template contains prohibited authority fields: {', '.join(prohibited)}"
        )
    unknown = sorted(set(payload) - _ALLOWED_FIELDS)
    if unknown:
        raise ValueError(f"prompt template contains unknown fields: {', '.join(unknown)}")
    missing = sorted(_REQUIRED_FIELDS - set(payload))
    if missing:
        raise ValueError(f"prompt template is missing fields: {', '.join(missing)}")

    prompt_id = str(payload["prompt_id"])
    if not _SAFE_PROMPT_ID.match(prompt_id):
        raise ValueError(f"prompt_id must match {_SAFE_PROMPT_ID.pattern}")
    authority = str(payload["authority"])
    if authority not in ALLOWED_AUTHORITIES:
        raise ValueError(
            f"prompt template authority must be one of: {', '.join(ALLOWED_AUTHORITIES)}"
        )
    body = str(payload["body"])
    if not body.strip():
        raise ValueError("prompt template body must not be empty")
    if len(body) > MAX_BODY_CHARS:
        raise ValueError(f"prompt template body must be at most {MAX_BODY_CHARS} characters")

    declared = payload.get("variables", [])
    if not isinstance(declared, list) or any(not isinstance(item, str) for item in declared):
        raise ValueError("variables must be a list of strings")
    found = tuple(dict.fromkeys(_VARIABLE.findall(body)))
    undeclared = sorted(set(found) - set(declared))
    if undeclared:
        raise ValueError(f"prompt template body uses undeclared variables: {', '.join(undeclared)}")

    return PromptTemplate(
        prompt_id=prompt_id,
        version=str(payload["version"]),
        title=str(payload["title"]),
        description=str(payload["description"]),
        body=body,
        authority=authority,
        variables=tuple(declared),
    )


def load_prompt_template(prompt_id: str, base_dir: Path | None = None) -> PromptTemplate:
    path = _prompt_path(prompt_id, base_dir)
    if not path.is_file():
        raise FileNotFoundError(f"prompt template not found: {prompt_id}")
    with path.open("r", encoding="utf-8") as stream:
        template = parse_prompt_template(yaml.safe_load(stream) or {})
    if template.prompt_id != prompt_id:
        raise ValueError("prompt template id mismatch")
    return template


def list_prompt_templates_with_errors(base_dir: Path | None = None) -> PromptTemplateList:
    directory = prompts_directory(base_dir)
    if not directory.is_dir():
        return PromptTemplateList()
    templates: list[PromptTemplate] = []
    errors: list[PromptTemplateError] = []
    for path in sorted(directory.glob("*.yaml")):
        try:
            with path.open("r", encoding="utf-8") as stream:
                template = parse_prompt_template(yaml.safe_load(stream) or {})
            if template.prompt_id != path.stem:
                raise ValueError(
                    f"prompt template id '{template.prompt_id}' does not match filename '{path.stem}'"
                )
            templates.append(template)
        except Exception as exc:
            errors.append(PromptTemplateError(prompt_path=path.name, reason=str(exc)))
    templates.sort(key=lambda item: item.prompt_id)
    return PromptTemplateList(templates=templates, errors=errors)
