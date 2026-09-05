from __future__ import annotations

from pathlib import Path

import pytest
from backend.app.extensions import skills as skills_module
from backend.app.extensions.skills import (
    list_skills_with_errors,
    load_skill_body,
    load_skill_manifest,
    parse_skill_frontmatter,
    resolve_skill_script,
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


def test_discovery_does_not_decode_or_read_the_instruction_body(tmp_path: Path) -> None:
    directory = write_skill(tmp_path, "release-notes")
    (directory / "SKILL.md").write_bytes(
        b"---\nname: Release notes\ndescription: d\nversion: '1'\n---\n" + b"\xff" * 100_000
    )

    result = list_skills_with_errors(tmp_path)

    assert [skill.skill_id for skill in result.skills] == ["release-notes"]


def test_requested_tools_are_recorded_as_an_untrusted_request_not_a_grant(tmp_path: Path) -> None:
    write_skill(tmp_path, "release-notes")

    skill = load_skill_manifest("release-notes", tmp_path)
    claims = skill.metadata_claims()

    assert claims["requested_capabilities"] == {"ids": ["search-public-web"], "trusted": False}
    assert skill.requested_tools == ("search-public-web",)
    # The manifest has no field through which a skill could grant itself anything.
    assert not hasattr(skill, "allowed_tools")


@pytest.mark.parametrize(
    "field", ["tool_policy: open", "trust: application", "enabled: true"]
)
def test_a_skill_cannot_declare_authority_for_itself(field: str) -> None:
    manifest = f"---\nname: X\ndescription: d\nversion: '1'\n{field}\n---\nbody"

    with pytest.raises(ValueError, match="prohibited authority fields"):
        parse_skill_frontmatter("x", manifest, "s")


def test_standard_agentskills_frontmatter_is_loaded_as_untrusted_metadata(tmp_path: Path) -> None:
    write_skill(
        tmp_path,
        "pdf-processing",
        "---\n"
        "name: pdf-processing\n"
        "description: Extract text from PDFs when documents need review.\n"
        "license: Apache-2.0\n"
        "compatibility: Requires Python 3.11\n"
        "metadata:\n  author: example\n"
        "allowed-tools: Bash(pdftotext:*) Read\n"
        "---\nbody",
    )

    skill = load_skill_manifest("pdf-processing", tmp_path)

    assert skill.version == ""
    assert skill.license == "Apache-2.0"
    assert skill.compatibility == "Requires Python 3.11"
    assert skill.metadata == {"author": "example"}
    assert skill.requested_tools == ("Bash(pdftotext:*)", "Read")
    assert skill.metadata_claims()["requested_capabilities"]["trusted"] is False


def test_application_skill_overrides_operator_skill_and_records_collision(tmp_path: Path) -> None:
    write_skill(tmp_path, "release-notes")
    config = tmp_path / "config"
    write_skill(config, "release-notes", MANIFEST.replace("Release notes", "Application release notes"))

    result = list_skills_with_errors(tmp_path, config_dir=config)

    assert [(skill.name, skill.trust, skill.provenance) for skill in result.skills] == [
        ("Application release notes", "application", "config/extensions/skills")
    ]
    assert [error.reason for error in result.errors] == ["application skill overrides operator skill"]


def test_repository_data_root_discovers_application_skills_without_an_explicit_config_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data = tmp_path / "data"
    config = tmp_path / "config"
    monkeypatch.setattr(skills_module, "DATA_DIR", data)
    monkeypatch.setattr(skills_module, "CONFIG_DIR", config)
    write_skill(data, "release-notes")
    write_skill(config, "release-notes", MANIFEST.replace("Release notes", "Application release notes"))

    result = skills_module.list_skills_with_errors(data)

    assert result.skills[0].trust == "application"


def test_script_symlink_escape_is_rejected(tmp_path: Path) -> None:
    directory = write_skill(
        tmp_path,
        "builder",
        "---\nname: Builder\ndescription: d\nversion: '1'\nscripts: [build.py]\n---\nbody",
    )
    outside = tmp_path / "outside.py"
    outside.write_text("print('outside')", encoding="utf-8")
    (directory / "build.py").symlink_to(outside)

    result = list_skills_with_errors(tmp_path)

    assert result.skills == []
    assert "contains a symlink" in result.errors[0].reason


def test_skill_manifest_symlink_is_rejected_for_discovery_and_direct_load(tmp_path: Path) -> None:
    directory = write_skill(tmp_path, "builder")
    outside = tmp_path / "outside.md"
    outside.write_text(MANIFEST, encoding="utf-8")
    (directory / "SKILL.md").unlink()
    (directory / "SKILL.md").symlink_to(outside)

    result = list_skills_with_errors(tmp_path)

    assert result.skills == []
    assert "must not be a symlink" in result.errors[0].reason
    with pytest.raises(ValueError, match="must not be a symlink"):
        load_skill_manifest("builder", tmp_path)


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


def test_standard_scripts_directory_is_discoverable_and_resolves_contained_scripts(tmp_path: Path) -> None:
    directory = write_skill(
        tmp_path,
        "builder",
        "---\nname: builder\ndescription: Build release artifacts.\n---\nbody",
    )
    scripts = directory / "scripts"
    scripts.mkdir()
    (scripts / "build.py").write_text("print('build')", encoding="utf-8")

    skill = list_skills_with_errors(tmp_path).skills[0]

    assert skill.has_scripts is True
    assert resolve_skill_script("builder", "build.py", tmp_path) == (scripts / "build.py").resolve()
    assert resolve_skill_script("builder", "scripts/build.py", tmp_path) == (scripts / "build.py").resolve()


@pytest.mark.parametrize("skill_id", ["../escape", "a/b"])
def test_unsafe_skill_ids_are_refused(skill_id: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe skill id"):
        load_skill_manifest(skill_id, tmp_path)
