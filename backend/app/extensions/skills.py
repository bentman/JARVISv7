from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from backend.app.core.paths import DATA_DIR

SKILLS_DIRNAME = "extensions/skills"
SKILL_MANIFEST = "SKILL.md"
_ALLOWED_FIELDS = {
    "name", "description", "version", "requested_tools", "references", "scripts", "assets",
}
_REQUIRED_FIELDS = {"name", "description", "version"}
# A skill is user-authored. It may request capability use; it may never grant itself
# authority, declare its own trust, or claim to be enabled.
_PROHIBITED_FIELDS = {
    "allowed_tools", "allowed-tools", "tool_policy", "tool_permissions", "trust",
    "trusted", "enabled", "routing_policy", "memory_policy", "safety_overrides",
    "hidden_instructions", "authority",
}
_SAFE_SKILL_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)
MAX_BODY_CHARS = 20_000


@dataclass(frozen=True, slots=True)
class SkillManifest:
    skill_id: str
    name: str
    description: str
    version: str
    source: str
    requested_tools: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    scripts: tuple[str, ...] = ()
    assets: tuple[str, ...] = ()

    @property
    def has_scripts(self) -> bool:
        return bool(self.scripts)

    def metadata_claims(self) -> dict[str, Any]:
        # Requested tools are a request recorded for the operator, never a grant.
        return {
            "requested_capabilities": {"ids": list(self.requested_tools), "trusted": False},
            "declared_files": {
                "references": list(self.references),
                "scripts": list(self.scripts),
                "assets": list(self.assets),
                "trusted": False,
            },
        }


@dataclass(frozen=True, slots=True)
class SkillError:
    skill_path: str
    reason: str


@dataclass(frozen=True, slots=True)
class SkillList:
    skills: list[SkillManifest] = field(default_factory=list)
    errors: list[SkillError] = field(default_factory=list)


def skills_directory(base_dir: Path | None = None) -> Path:
    return (base_dir or DATA_DIR) / SKILLS_DIRNAME


def _skill_dir(skill_id: str, base_dir: Path | None = None) -> Path:
    if skill_id != skill_id.strip() or any(token in skill_id for token in ("/", "\\", "..")):
        raise ValueError(f"unsafe skill id: {skill_id}")
    return skills_directory(base_dir) / skill_id


def _relative_paths(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    for item in value:
        candidate = Path(item)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"{field_name} entries must stay inside the skill directory: {item}")
    return tuple(value)


def parse_skill_frontmatter(skill_id: str, text: str, source: str) -> SkillManifest:
    match = _FRONTMATTER.match(text)
    if match is None:
        raise ValueError("SKILL.md must begin with a YAML frontmatter block")
    payload = yaml.safe_load(match.group(1)) or {}
    if not isinstance(payload, dict):
        raise ValueError("SKILL.md frontmatter must be a mapping")

    prohibited = sorted(_PROHIBITED_FIELDS & set(payload))
    if prohibited:
        raise ValueError(
            f"skill frontmatter contains prohibited authority fields: {', '.join(prohibited)}"
        )
    unknown = sorted(set(payload) - _ALLOWED_FIELDS)
    if unknown:
        raise ValueError(f"skill frontmatter contains unknown fields: {', '.join(unknown)}")
    missing = sorted(_REQUIRED_FIELDS - set(payload))
    if missing:
        raise ValueError(f"skill frontmatter is missing fields: {', '.join(missing)}")
    if not _SAFE_SKILL_ID.match(skill_id):
        raise ValueError(f"skill id must match {_SAFE_SKILL_ID.pattern}")

    requested = payload.get("requested_tools", [])
    if not isinstance(requested, list) or any(not isinstance(item, str) for item in requested):
        raise ValueError("requested_tools must be a list of strings")

    return SkillManifest(
        skill_id=skill_id,
        name=str(payload["name"]),
        description=str(payload["description"]),
        version=str(payload["version"]),
        source=source,
        requested_tools=tuple(requested),
        references=_relative_paths(payload.get("references"), "references"),
        scripts=_relative_paths(payload.get("scripts"), "scripts"),
        assets=_relative_paths(payload.get("assets"), "assets"),
    )


def load_skill_manifest(skill_id: str, base_dir: Path | None = None) -> SkillManifest:
    manifest_path = _skill_dir(skill_id, base_dir) / SKILL_MANIFEST
    if not manifest_path.is_file():
        raise FileNotFoundError(f"skill not found: {skill_id}")
    text = manifest_path.read_text(encoding="utf-8")
    return parse_skill_frontmatter(skill_id, text, source=str(manifest_path))


def load_skill_body(skill_id: str, base_dir: Path | None = None) -> str:
    """Second disclosure step: the body is read only when explicitly requested."""
    manifest_path = _skill_dir(skill_id, base_dir) / SKILL_MANIFEST
    if not manifest_path.is_file():
        raise FileNotFoundError(f"skill not found: {skill_id}")
    match = _FRONTMATTER.match(manifest_path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError("SKILL.md must begin with a YAML frontmatter block")
    return match.group(2)[:MAX_BODY_CHARS]


def list_skills_with_errors(base_dir: Path | None = None) -> SkillList:
    directory = skills_directory(base_dir)
    if not directory.is_dir():
        return SkillList()
    skills: list[SkillManifest] = []
    errors: list[SkillError] = []
    for child in sorted(directory.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / SKILL_MANIFEST
        if not manifest_path.is_file():
            errors.append(SkillError(skill_path=child.name, reason=f"missing {SKILL_MANIFEST}"))
            continue
        try:
            # Frontmatter only: the body and every referenced file stay unread here.
            skills.append(
                parse_skill_frontmatter(
                    child.name, manifest_path.read_text(encoding="utf-8"), str(manifest_path)
                )
            )
        except Exception as exc:
            errors.append(SkillError(skill_path=child.name, reason=str(exc)))
    skills.sort(key=lambda item: item.skill_id)
    return SkillList(skills=skills, errors=errors)
