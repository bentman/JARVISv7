from __future__ import annotations

from pathlib import Path

import pytest
from backend.app.extensions.skills import (
    list_skills_with_errors,
    load_skill_body,
    load_skill_manifest,
    parse_skill_frontmatter,
)

BODY = "# Release notes\n\nThe full procedure lives here."
MANIFEST = (
    "---\n"
    "name: Release notes\n"
    "description: Draft release notes from a changelog.\n"
    'version: "1"\n'
    "requested_tools: [search-public-web]\n"
    "---\n"
    f"{BODY}\n"
)


def write_skill(root: Path, skill_id: str, manifest: str = MANIFEST) -> Path:
    directory = root / "extensions" / "skills" / skill_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(manifest, encoding="utf-8")
    return directory


def test_discovery_reads_frontmatter_without_reading_the_body(tmp_path: Path) -> None:
    write_skill(tmp_path, "release-notes")

    result = list_skills_with_errors(tmp_path)
    skill = result.skills[0]

    assert (skill.skill_id, skill.name, skill.version) == ("release-notes", "Release notes", "1")
    # Progressive disclosure: nothing in the listing carries the body.
    assert BODY not in str(result)
    assert BODY in load_skill_body("release-notes", tmp_path)


def test_requested_tools_are_recorded_as_an_untrusted_request_not_a_grant(tmp_path: Path) -> None:
    write_skill(tmp_path, "release-notes")

    skill = load_skill_manifest("release-notes", tmp_path)
    claims = skill.metadata_claims()

    assert claims["requested_capabilities"] == {"ids": ["search-public-web"], "trusted": False}
    assert skill.requested_tools == ("search-public-web",)
    # The manifest has no field through which a skill could grant itself anything.
    assert not hasattr(skill, "allowed_tools")


@pytest.mark.parametrize(
    "field", ["allowed-tools: [shell]", "tool_policy: open", "trust: application", "enabled: true"]
)
def test_a_skill_cannot_declare_authority_for_itself(field: str) -> None:
    manifest = f"---\nname: X\ndescription: d\nversion: '1'\n{field}\n---\nbody"

    with pytest.raises(ValueError, match="prohibited authority fields"):
        parse_skill_frontmatter("x", manifest, "s")


@pytest.mark.parametrize("path", ["../../etc/passwd", "/etc/passwd", "a/../../b"])
def test_declared_files_cannot_escape_the_skill_directory(path: str) -> None:
    manifest = f"---\nname: X\ndescription: d\nversion: '1'\nscripts: ['{path}']\n---\nbody"

    with pytest.raises(ValueError, match="must stay inside the skill directory"):
        parse_skill_frontmatter("x", manifest, "s")


def test_frontmatter_is_required(tmp_path: Path) -> None:
    write_skill(tmp_path, "bare", "no frontmatter here\n")

    result = list_skills_with_errors(tmp_path)

    assert result.skills == []
    assert "must begin with a YAML frontmatter block" in result.errors[0].reason


def test_a_directory_without_a_manifest_is_reported(tmp_path: Path) -> None:
    (tmp_path / "extensions" / "skills" / "empty").mkdir(parents=True)

    result = list_skills_with_errors(tmp_path)

    assert [error.reason for error in result.errors] == ["missing SKILL.md"]


def test_one_malformed_skill_does_not_break_discovery(tmp_path: Path) -> None:
    write_skill(tmp_path, "good")
    write_skill(tmp_path, "bad", "---\nname: B\n---\nbody")

    result = list_skills_with_errors(tmp_path)

    assert [skill.skill_id for skill in result.skills] == ["good"]
    assert [error.skill_path for error in result.errors] == ["bad"]


def test_a_missing_skills_root_is_empty_not_an_error(tmp_path: Path) -> None:
    result = list_skills_with_errors(tmp_path)

    assert result.skills == [] and result.errors == []


def test_a_script_bearing_skill_is_flagged_so_it_cannot_look_runnable(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        "builder",
        "---\nname: Builder\ndescription: d\nversion: '1'\nscripts: [build.py]\n---\nbody",
    )

    skill = list_skills_with_errors(tmp_path).skills[0]

    assert skill.has_scripts is True
    assert skill.metadata_claims()["declared_files"]["scripts"] == ["build.py"]


@pytest.mark.parametrize("skill_id", ["../escape", "a/b"])
def test_unsafe_skill_ids_are_refused(skill_id: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe skill id"):
        load_skill_manifest(skill_id, tmp_path)
