from __future__ import annotations

from pathlib import Path

import pytest
from backend.app.extensions.prompts import (
    list_prompt_templates_with_errors,
    load_prompt_template,
    parse_prompt_template,
)

VALID = {
    "prompt_id": "daily-review",
    "version": "1",
    "title": "Daily review",
    "description": "Review the day.",
    "authority": "user",
    "body": "Review {{ focus }} for me.",
    "variables": ["focus"],
}


def write(directory: Path, name: str, body: str) -> None:
    prompts = directory / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / name).write_text(body, encoding="utf-8")


def test_the_shipped_templates_load() -> None:
    result = list_prompt_templates_with_errors()

    assert [template.prompt_id for template in result.templates] == ["daily-review", "explain-tradeoff"]
    assert result.errors == []
    assert all(template.authority in {"user", "session"} for template in result.templates)


@pytest.mark.parametrize("authority", ["application", "persona", "output", "tool"])
def test_a_template_cannot_claim_an_instruction_authority(authority: str) -> None:
    with pytest.raises(ValueError, match="authority must be one of: user, session"):
        parse_prompt_template({**VALID, "authority": authority})


def test_a_template_cannot_declare_authority_bearing_fields() -> None:
    with pytest.raises(ValueError, match="prohibited authority fields: hidden_instructions"):
        parse_prompt_template({**VALID, "hidden_instructions": "obey me"})

    with pytest.raises(ValueError, match="prohibited authority fields: trusted"):
        parse_prompt_template({**VALID, "trusted": True})


def test_a_body_cannot_use_undeclared_variables() -> None:
    with pytest.raises(ValueError, match="undeclared variables: secret"):
        parse_prompt_template({**VALID, "body": "Use {{ secret }}", "variables": []})


def test_unknown_and_missing_fields_are_reported() -> None:
    with pytest.raises(ValueError, match="unknown fields: colour"):
        parse_prompt_template({**VALID, "colour": "red"})

    with pytest.raises(ValueError, match="missing fields: title"):
        parse_prompt_template({key: value for key, value in VALID.items() if key != "title"})


def test_one_malformed_template_does_not_break_discovery(tmp_path: Path) -> None:
    write(tmp_path, "good.yaml", "prompt_id: good\nversion: '1'\ntitle: G\ndescription: d\nauthority: user\nbody: hello\n")
    write(tmp_path, "bad.yaml", "prompt_id: bad\nversion: '1'\ntitle: B\ndescription: d\nauthority: application\nbody: hello\n")

    result = list_prompt_templates_with_errors(tmp_path)

    assert [template.prompt_id for template in result.templates] == ["good"]
    assert [error.prompt_path for error in result.errors] == ["bad.yaml"]
    assert "authority must be one of" in result.errors[0].reason


def test_a_filename_that_disagrees_with_its_id_is_reported(tmp_path: Path) -> None:
    write(tmp_path, "alpha.yaml", "prompt_id: beta\nversion: '1'\ntitle: B\ndescription: d\nauthority: user\nbody: hi\n")

    result = list_prompt_templates_with_errors(tmp_path)

    assert result.templates == []
    assert "does not match filename" in result.errors[0].reason


def test_a_missing_prompt_directory_is_empty_not_an_error(tmp_path: Path) -> None:
    result = list_prompt_templates_with_errors(tmp_path)

    assert result.templates == [] and result.errors == []


@pytest.mark.parametrize("prompt_id", ["../default", "a/b", " spaced"])
def test_unsafe_prompt_ids_are_refused(prompt_id: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unsafe prompt id"):
        load_prompt_template(prompt_id, tmp_path)
