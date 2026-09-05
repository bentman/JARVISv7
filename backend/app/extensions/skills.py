from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from backend.app.core.paths import CONFIG_DIR, DATA_DIR

SKILLS_DIRNAME = "extensions/skills"
SKILL_MANIFEST = "SKILL.md"
_ALLOWED_FIELDS = {
    # ``version`` and ``requested_tools`` are the original JARVIS manifest
    # fields.  The remaining names include the Agent Skills frontmatter.
    "name", "description", "version", "requested_tools", "references", "scripts", "assets",
    "license", "compatibility", "metadata", "allowed-tools",
}
_REQUIRED_FIELDS = {"name", "description"}
# A skill is user-authored. It may request capability use; it may never grant itself
# authority, declare its own trust, or claim to be enabled.
_PROHIBITED_FIELDS = {
    "allowed_tools", "tool_policy", "tool_permissions", "trust",
    "trusted", "enabled", "routing_policy", "memory_policy", "safety_overrides",
    "hidden_instructions", "authority",
}
_SAFE_SKILL_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_STANDARD_SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)
MAX_BODY_CHARS = 20_000
MAX_FRONTMATTER_CHARS = 16_000


@dataclass(frozen=True, slots=True)
class SkillManifest:
    skill_id: str
    name: str
    description: str
    source: str
    version: str = ""
    provenance: str = "data/extensions/skills"
    trust: str = "external"
    requested_tools: tuple[str, ...] = ()
    references: tuple[str, ...] = ()
    scripts: tuple[str, ...] = ()
    assets: tuple[str, ...] = ()
    license: str | None = None
    compatibility: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    scripts_directory_present: bool = False

    @property
    def has_scripts(self) -> bool:
        return bool(self.scripts) or self.scripts_directory_present

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
    """Return the operator-owned skill root (the legacy public helper)."""
    return (base_dir or DATA_DIR) / SKILLS_DIRNAME


def application_skills_directory(base_dir: Path | None = None) -> Path:
    return (base_dir or CONFIG_DIR) / SKILLS_DIRNAME


def operator_skills_directory(base_dir: Path | None = None) -> Path:
    return skills_directory(base_dir)


def _skill_dir(skill_id: str, base_dir: Path | None = None) -> Path:
    if skill_id != skill_id.strip() or any(token in skill_id for token in ("/", "\\", "..")):
        raise ValueError(f"unsafe skill id: {skill_id}")
    return operator_skills_directory(base_dir) / skill_id


def _relative_paths(value: Any, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    for item in value:
        candidate = Path(item)
        # Path.is_absolute() is host-OS-dependent (a leading "/" is not absolute
        # under Windows pathlib semantics without a drive letter), so a declared
        # POSIX-style root path must be checked independently of the host platform.
        if (
            candidate.is_absolute()
            or candidate.drive
            or PurePosixPath(item).is_absolute()
            or ".." in candidate.parts
        ):
            raise ValueError(f"{field_name} entries must stay inside the skill directory: {item}")
    return tuple(value)


def _optional_string(payload: dict[str, Any], key: str, max_chars: int | None = None) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    if max_chars is not None and len(value) > max_chars:
        raise ValueError(f"{key} must be at most {max_chars} characters")
    return value


def _metadata(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict) or any(
        not isinstance(key, str) or not isinstance(item, str) for key, item in value.items()
    ):
        raise ValueError("metadata must be a mapping of strings")
    return dict(value)


def _requested_tools(payload: dict[str, Any]) -> tuple[str, ...]:
    requested = payload.get("requested_tools", [])
    standard = payload.get("allowed-tools", "")
    if not isinstance(requested, list) or any(not isinstance(item, str) for item in requested):
        raise ValueError("requested_tools must be a list of strings")
    if not isinstance(standard, str):
        raise ValueError("allowed-tools must be a space-separated string")
    return tuple(dict.fromkeys([*requested, *standard.split()]))


def parse_skill_frontmatter(
    skill_id: str,
    text: str,
    source: str,
    *,
    trust: str = "external",
    provenance: str | None = None,
) -> SkillManifest:
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
    if trust not in {"application", "external"}:
        raise ValueError("trust must be application or external")

    name = _optional_string(payload, "name", 64)
    description = _optional_string(payload, "description", 1024)
    assert name is not None and description is not None
    # Legacy JARVIS manifests use ``version`` and a display name. A manifest
    # without it follows Agent Skills, whose name is its directory name.
    if "version" not in payload and (name != skill_id or not _STANDARD_SKILL_NAME.match(name)):
        raise ValueError("standard skill name must match the directory name")

    return SkillManifest(
        skill_id=skill_id,
        name=name,
        description=description,
        version=str(payload.get("version", "")),
        source=source,
        provenance=provenance or ("config/extensions/skills" if trust == "application" else "data/extensions/skills"),
        trust=trust,
        requested_tools=_requested_tools(payload),
        references=_relative_paths(payload.get("references"), "references"),
        scripts=_relative_paths(payload.get("scripts"), "scripts"),
        assets=_relative_paths(payload.get("assets"), "assets"),
        license=_optional_string(payload, "license"),
        compatibility=_optional_string(payload, "compatibility", 500),
        metadata=_metadata(payload.get("metadata")),
    )


def _contained_skill_path(skill_root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.drive or PurePosixPath(relative).is_absolute() or ".." in candidate.parts:
        raise ValueError(f"skill path escapes the skill directory: {relative}")
    raw = skill_root / candidate
    cursor = skill_root
    for part in candidate.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"skill path contains a symlink: {relative}")
    resolved_root = skill_root.resolve()
    resolved = raw.resolve()
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise ValueError(f"skill path escapes the skill directory: {relative}")
    return resolved


def _validate_script_paths(manifest: SkillManifest, skill_root: Path) -> None:
    for script in manifest.scripts:
        candidate = skill_root / script
        if candidate.exists() or candidate.is_symlink():
            _contained_skill_path(skill_root, script)


def _with_scripts_directory(manifest: SkillManifest, skill_root: Path) -> SkillManifest:
    scripts = skill_root / "scripts"
    return replace(manifest, scripts_directory_present=scripts.is_dir() and not scripts.is_symlink())


def _read_frontmatter(manifest_path: Path) -> str:
    """Read only the YAML header during catalog discovery."""
    if manifest_path.is_symlink():
        raise ValueError("SKILL.md must not be a symlink")
    chunks: list[str] = []
    total = 0
    with manifest_path.open("rb") as stream:
        first = stream.readline().decode("utf-8")
        if first.strip() != "---":
            raise ValueError("SKILL.md must begin with a YAML frontmatter block")
        chunks.append(first)
        total += len(first)
        for raw_line in stream:
            line = raw_line.decode("utf-8")
            total += len(line)
            if total > MAX_FRONTMATTER_CHARS:
                raise ValueError("SKILL.md frontmatter exceeds the allowed size")
            chunks.append(line)
            if line.strip() == "---":
                return "".join(chunks)
    raise ValueError("SKILL.md must begin with a YAML frontmatter block")


def _select_root(root: Path, skill_id: str) -> Path | None:
    candidate = root / skill_id
    if not candidate.exists() and not candidate.is_symlink():
        return None
    if candidate.is_symlink():
        raise ValueError(f"skill path contains a symlink: {skill_id}")
    resolved_root = root.resolve()
    resolved_candidate = candidate.resolve()
    if resolved_candidate != resolved_root and resolved_root not in resolved_candidate.parents:
        raise ValueError(f"skill path escapes the skills root: {skill_id}")
    manifest = candidate / SKILL_MANIFEST
    if manifest.is_symlink():
        raise ValueError("SKILL.md must not be a symlink")
    return candidate if manifest.is_file() else None


def _select_skill_path(
    skill_id: str, data_dir: Path | None, config_dir: Path | None
) -> tuple[Path, str]:
    if skill_id != skill_id.strip() or any(token in skill_id for token in ("/", "\\", "..")):
        raise ValueError(f"unsafe skill id: {skill_id}")
    application = _select_root(application_skills_directory(config_dir), skill_id) if config_dir is not None else None
    operator = _select_root(operator_skills_directory(data_dir), skill_id)
    if application is not None:
        return application, "application"
    if operator is not None:
        return operator, "external"
    raise FileNotFoundError(f"skill not found: {skill_id}")


def load_skill_manifest(
    skill_id: str, base_dir: Path | None = None, *, config_dir: Path | None = None
) -> SkillManifest:
    effective_config = CONFIG_DIR if base_dir is None and config_dir is None else config_dir
    skill_root, trust = _select_skill_path(skill_id, base_dir, effective_config)
    manifest_path = skill_root / SKILL_MANIFEST
    if not manifest_path.is_file():
        raise FileNotFoundError(f"skill not found: {skill_id}")
    text = _read_frontmatter(manifest_path)
    manifest = parse_skill_frontmatter(skill_id, text, source=str(manifest_path), trust=trust)
    _validate_script_paths(manifest, skill_root)
    return _with_scripts_directory(manifest, skill_root)


def load_skill_body(
    skill_id: str, base_dir: Path | None = None, *, config_dir: Path | None = None
) -> str:
    """Second disclosure step: the body is read only when explicitly requested."""
    effective_config = CONFIG_DIR if base_dir is None and config_dir is None else config_dir
    skill_root, _ = _select_skill_path(skill_id, base_dir, effective_config)
    manifest_path = skill_root / SKILL_MANIFEST
    if not manifest_path.is_file():
        raise FileNotFoundError(f"skill not found: {skill_id}")
    if manifest_path.is_symlink():
        raise ValueError("SKILL.md must not be a symlink")
    match = _FRONTMATTER.match(manifest_path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError("SKILL.md must begin with a YAML frontmatter block")
    return match.group(2)[:MAX_BODY_CHARS]


def resolve_skill_script(
    skill_id: str, script: str, base_dir: Path | None = None, *, config_dir: Path | None = None
) -> Path:
    effective_config = CONFIG_DIR if base_dir is None and config_dir is None else config_dir
    skill_root, _ = _select_skill_path(skill_id, base_dir, effective_config)
    manifest = load_skill_manifest(skill_id, base_dir, config_dir=effective_config)
    if script in manifest.scripts:
        relative = script
    else:
        candidate = Path(script)
        relative = script if candidate.parts and candidate.parts[0] == "scripts" else str(Path("scripts") / candidate)
    if not relative.startswith("scripts/") and relative != "scripts":
        raise ValueError(f"script is not declared by skill: {script}")
    path = _contained_skill_path(skill_root, relative)
    if not path.is_file():
        raise ValueError(f"skill script is not a file: {script}")
    return path


def _discover_root(directory: Path, trust: str) -> SkillList:
    skills: list[SkillManifest] = []
    errors: list[SkillError] = []
    if not directory.is_dir():
        return SkillList()
    for child in sorted(directory.iterdir()):
        if not child.is_dir():
            continue
        manifest_path = child / SKILL_MANIFEST
        if not manifest_path.is_file():
            errors.append(SkillError(skill_path=child.name, reason=f"missing {SKILL_MANIFEST}"))
            continue
        try:
            # Frontmatter only: the body and every referenced file stay unread here.
            root = directory.resolve()
            resolved_child = child.resolve()
            if resolved_child != root and root not in resolved_child.parents:
                raise ValueError("skill directory escapes the skills root")
            if manifest_path.is_symlink():
                raise ValueError("SKILL.md must not be a symlink")
            manifest = parse_skill_frontmatter(
                child.name, _read_frontmatter(manifest_path), str(manifest_path), trust=trust
            )
            _validate_script_paths(manifest, child)
            skills.append(_with_scripts_directory(manifest, child))
        except Exception as exc:
            errors.append(SkillError(skill_path=child.name, reason=str(exc)))
    return SkillList(skills=skills, errors=errors)


def list_skills_with_errors(
    base_dir: Path | None = None, *, config_dir: Path | None = None
) -> SkillList:
    """Discover application then operator skills without reading instruction bodies.

    Passing ``base_dir`` keeps the legacy single-root behavior unless a config root is
    also supplied; production callers omit it and therefore observe both roots.
    """
    operator_root = operator_skills_directory(base_dir)
    effective_config = config_dir
    if effective_config is None and (base_dir is None or base_dir == DATA_DIR):
        effective_config = CONFIG_DIR
    application_root = application_skills_directory(effective_config) if effective_config else None
    application = _discover_root(application_root, "application") if application_root else SkillList()
    operator = _discover_root(operator_root, "external")
    skills = {skill.skill_id: skill for skill in application.skills}
    errors = [*application.errors]
    for skill in operator.skills:
        if skill.skill_id in skills:
            errors.append(SkillError(skill_path=skill.skill_id, reason="application skill overrides operator skill"))
            continue
        skills[skill.skill_id] = skill
    errors.extend(operator.errors)
    return SkillList(skills=sorted(skills.values(), key=lambda item: item.skill_id), errors=errors)
